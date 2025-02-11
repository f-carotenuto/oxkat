import numpy as np
import os
import math

path = os.getcwd()

opfile = 'imfit_results_images_1543_8sec_imstat.txt'
f = open(opfile,'w')


# list to store files
imagelist = []
# Iterate directory
for file in os.listdir(path):
    # check only text files
    if file.endswith('image.fits'):
        imagelist.append(file)

imagelist.sort()

print(imagelist)


n_int = len(imagelist)

flux_mjy = np.zeros(len(imagelist))
error_mjy = np.zeros(len(imagelist))

index = 0

for i in imagelist:
    try:
        fit_result = imfit(imagename=i, region='/scratch3/users/francesco.carotenuto/scratch1/reg_1543_ds9.reg', logfile='log'+i+'.log')
        bkg_noise = imstat(imagename=i, region='/scratch3/users/francesco.carotenuto/scratch1/reg_1543_bkg.reg', logfile='log'+i+'BKG.log')

        flux_mjy[index] = 1000 * fit_result['results']['component0']['peak']['value']
        error_mjy[index] = 1000 * bkg_noise['rms']
        #error_mjy[index] = 1000 * fit_result['results']['component0']['peak']['error']

        print(1000 * fit_result['results']['component0']['peak']['value'])
        print(error_mjy[index])
    
    except Exception as e:
        # If the task fails, assign NaN to flux and error
        flux_mjy[index] = np.nan
        error_mjy[index] = np.nan

        print("imfit failed for image {}, setting flux and error to NaN. Error: {}".format(i, e))

    
    f.write("%f %f %f\n" % (index, flux_mjy[index], error_mjy[index]))
    index += 1

f.close()