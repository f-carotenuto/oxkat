import os
import numpy as np
from astropy.io import fits
from astropy.time import Time
import argparse

# Set up argument parsing
parser = argparse.ArgumentParser(description="Append MJD to existing file with obs_duration adjustment")
parser.add_argument('--obs_duration', type=float, required=True, help='Observation duration in seconds')
args = parser.parse_args()

# Path to the directory with FITS images and the result file
path = os.getcwd()
opfile = 'imfit_results_images_1543_8sec_imstat.txt'
output_file_with_mjd = 'imfit_results_images_1543_8sec_imstat_with_mjd.txt'

# Observation duration (in seconds), adjusting by half for central time
obs_duration = args.obs_duration
half_duration_in_days = obs_duration / (2 * 86400)  # Convert seconds to fractional days

# List to store files
imagelist = []
# Iterate directory for FITS files
for file in os.listdir(path):
    if file.endswith('image.fits'):
        imagelist.append(file)

imagelist.sort()

print("Images found:", imagelist)

n_int = len(imagelist)
mjd_times = np.zeros(len(imagelist))

# Read each FITS file and extract the DATE-OBS, then convert to MJD
for index, i in enumerate(imagelist):
    try:
        # Reading the FITS header to get DATE-OBS
        with fits.open(os.path.join(path, i)) as hdul:
            header = hdul[0].header
            date_obs = header['DATE-OBS']  # Get the DATE-OBS keyword

            # Convert DATE-OBS to MJD and adjust for central time
            t = Time(date_obs, format='isot', scale='utc')
            mjd_times[index] = t.mjd + half_duration_in_days  # Adjust MJD for central time
            
            print("DATE-OBS: {}, MJD (adjusted): {}".format(date_obs, mjd_times[index]))

    except Exception as e:
        mjd_times[index] = np.nan  # Assign NaN if any error occurs
        print("Failed to read DATE-OBS for image {}. Error: {}".format(i, e))

# Now, read the original file and append MJD to it
with open(opfile, 'r') as original_file, open(output_file_with_mjd, 'w') as new_file:
    lines = original_file.readlines()

    for index, line in enumerate(lines):
        # Append MJD to each line of the original file
        new_line = "{} {:.6f}\n".format(line.strip(), mjd_times[index])
        new_file.write(new_line)

print("MJD values (adjusted for obs_duration) have been appended to the file:", output_file_with_mjd)