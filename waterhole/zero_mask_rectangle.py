#!/usr/bin/env python
# ian.heywood@physics.ox.ac.uk

import glob
import numpy
import shutil
from astropy import wcs
from astropy.io import fits
from optparse import OptionParser
import re

# ---------------------------------------------------------------------------------------

def hms2deg(hms,delimiter=':'):
    """
    Right ascension string in hms to float in decimal degrees
    """
    h,m,s = hms.split(delimiter)
    h = float(h)
    m = float(m)
    s = float(s)
    deg = 15.0*(h+(m/60.0)+(s/3600.0))
    return deg

def dms2deg(dms):
    """
    Converts a declination string in various formats (e.g., -48:47:22.0742, -048.47.22.0742)
    to a float in decimal degrees.
    """
    # Define regex pattern to match both colon and dot formats
    match = re.match(r'([+-]?)(\d+)[.:](\d+)[.:](\d+)', dms)
    
    if not match:
        raise ValueError(f"Declination format not recognized: {dms}")

    # Extract matched groups
    sign = -1.0 if match.group(1) == '-' else 1.0
    d = float(match.group(2))
    m = float(match.group(3))
    s = float(match.group(4))

    # Convert to decimal degrees
    deg = sign * (d + (m / 60.0) + (s / 3600.0))
    return deg

def arcsec2deg(value):
    return float(value) / 3600.0


def process_region_file(region_file):
    """
    Extract RA, Dec, width, and height as floats in degrees
    from a CRTFv0 region file containing centerbox rectangles
    """
    rectangles = []
    with open(region_file, 'r') as f:
        for line in f:
            if line.startswith('centerbox'):
                # Improved regex to capture RA, Dec, width, and height only
                match = re.search(r'centerbox \[\[([\d:.+-]+),\s*([\d:.+-]+)\],\s*\[([\d.]+)arcsec,\s*([\d.]+)arcsec\]', line)
                if match:
                    # Extract the matched groups for coordinates and dimensions
                    ra_str = match.group(1)
                    dec_str = match.group(2)
                    width_str = match.group(3)
                    height_str = match.group(4)
                    
                    # Convert RA, Dec, width, and height to degrees
                    ra = hms2deg(ra_str)
                    dec = dms2deg(dec_str)
                    width = arcsec2deg(width_str)
                    height = arcsec2deg(height_str)
                    
                    # Append the rectangle (RA, Dec, width, height) to the list
                    rectangles.append((ra, dec, width, height))
                else:
                    print(f"Skipping line due to unexpected format: {line}")
    return rectangles

def get_image(fits_file):
    """
    Get the image data from a FITS file
    """
    input_hdu = fits.open(fits_file)[0]
    if len(input_hdu.data.shape) == 2:
        image = numpy.array(input_hdu.data[:,:])
    elif len(input_hdu.data.shape) == 3:
        image = numpy.array(input_hdu.data[0,:,:])
    else:
        image = numpy.array(input_hdu.data[0,0,:,:])
    return image

def flush_fits(image, fits_file):
    """
    Write 2D numpy array image to fits_file
    """
    f = fits.open(fits_file, mode='update')
    input_hdu = f[0]
    if len(input_hdu.data.shape) == 2:
        input_hdu.data[:,:] = image
    elif len(input_hdu.data.shape) == 3:
        input_hdu.data[0,:,:] = image
    else:
        input_hdu.data[0,0,:,:] = image
    f.flush()

def apply_rectangle(image, xpix, ypix, wpix, hpix, invert):
    """
    Apply a rectangle with values of 0 in a region of width wpix and height hpix centered at xpix,ypix
    """
    x_min = int(xpix - wpix / 2)
    x_max = int(xpix + wpix / 2)
    y_min = int(ypix - hpix / 2)
    y_max = int(ypix + hpix / 2)
    if invert:
        image[y_min:y_max, x_min:x_max] = 0.0
    else:
        image[y_min:y_max, x_min:x_max] = 0.0
    return image

def fmt(xx):
    return str(round(xx,5))

def spacer():
    print('--------------|---------------------------------------------')

# ---------------------------------------------------------------------------------------

def main():
    parser = OptionParser(usage='%prog [options]')
    parser.add_option('--region', dest='region_file', help='DS9 region file')
    parser.add_option('--fitsfile', dest='fits_file', help='FITS image')
    parser.add_option('--invert', dest='invert', help='Remove region instead of only keeping it', action='store_true', default=False)
    (options, args) = parser.parse_args()
    region_file = options.region_file
    fits_prefix = options.fits_file
    invert = options.invert

    rectangles = process_region_file(region_file)
    suffix = region_file.split('/')[-1].split('.')[0]

    spacer()
    print('DS9 region    : ' + region_file)
    print('Contains      : ' + str(len(rectangles)) + ' rectangles')
    print('Model suffix  : ' + suffix)
    spacer()

    print('Reading       : ' + fits_prefix)

    fitslist = sorted(glob.glob(f'{fits_prefix}*-model.fits'))
    
    for fitsfile in fitslist:

        print('Fixing NaNs   : ' + fitsfile)

        img = get_image(fitsfile)
        mask = img
        

        hdulist = fits.open(fitsfile)
        w = wcs.WCS(hdulist[0].header)
        ref_pix1 = hdulist[0].header['CRPIX1']
        ref_pix2 = hdulist[0].header['CRPIX2']
        pixscale = abs(hdulist[0].header['CDELT2'])

        maxval = numpy.max(img)
        if numpy.isnan(maxval):
                new_img = numpy.zeros((img.shape[0],img.shape[1]))
                print('              : ' + 'zeroing NaN model')
                flush_fits(new_img, fitsfile)
        else:
                print('              : ' + 'non-NaN, max = ', maxval)

        for rectangle in rectangles:
            ra, dec, width, height = rectangle
            coord = (ra, dec, 0, 0)
            pixels = w.wcs_world2pix([coord], 0)
            xpix = pixels[0][0]
            ypix = pixels[0][1]
            wpix = width / pixscale
            hpix = height / pixscale
            print('Masking       : sky ' + fmt(ra) + ' ' + fmt(dec) + ' ' + fmt(width) + ' ' + fmt(height))
            print('              : pixel ' + fmt(xpix) + ' ' + fmt(ypix) + ' ' + fmt(wpix) + ' ' + fmt(hpix))
            mask = apply_rectangle(mask, xpix, ypix, wpix, hpix, invert)

        masked_img = mask
        masked_fits = fitsfile.replace(fits_prefix, f'{fits_prefix}-{suffix}')
        print('Writing       : ' + masked_fits)
        shutil.copyfile(fitsfile, masked_fits)
        flush_fits(masked_img, masked_fits)
        spacer()

if __name__ == '__main__':
    main()
