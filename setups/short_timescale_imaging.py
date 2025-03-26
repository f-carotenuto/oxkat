
#!/usr/bin/env python
# ian.heywood@physics.ox.ac.uk


import glob
import json
import os
import os.path as o
import sys
import subprocess
import pickle
import numpy
sys.path.append(o.abspath(o.join(o.dirname(sys.modules[__name__].__file__), "..")))


from oxkat import generate_jobs as gen
from oxkat import config as cfg


def get_scan_times(scanpickle):
    scan_times = []
    ss = pickle.load(open(scanpickle,'rb'))
    fields = []
    for ii in ss:
        fields.append(ii[1])
    fields = numpy.unique(fields).tolist()
    for field in fields:
        scans = []
        intervals = []
        for ii in ss:
            if ii[1] == field:
                scans.append(ii[0])
                intervals.append(ii[5])
        scan_times.append((field,scans,intervals))
    return scan_times


def main():

    USE_SINGULARITY = cfg.USE_SINGULARITY

    gen.preamble()
    print(gen.col()+'short timescale imaging setup')
    gen.print_spacer()


    # ------------------------------------------------------------------------------
    #
    # Setup paths, required containers, infrastructure
    #
    # ------------------------------------------------------------------------------


    OXKAT = cfg.OXKAT
    DATA = cfg.DATA
    GAINTABLES = cfg.GAINTABLES
    IMAGES = cfg.IMAGES
    SCRIPTS = cfg.SCRIPTS
    TOOLS = cfg.TOOLS
    WATERHOLE = cfg.WATERHOLE

    gen.setup_dir(GAINTABLES)
    gen.setup_dir(IMAGES)
    gen.setup_dir(cfg.LOGS)
    gen.setup_dir(cfg.SCRIPTS)


    INFRASTRUCTURE, CONTAINER_PATH = gen.set_infrastructure(sys.argv)
    if CONTAINER_PATH is not None:
        CONTAINER_RUNNER='singularity exec '
    else:
        CONTAINER_RUNNER=''


    CUBICAL_CONTAINER = gen.get_container(CONTAINER_PATH,cfg.CUBICAL_PATTERN,USE_SINGULARITY)
    WSCLEAN_CONTAINER = gen.get_container(CONTAINER_PATH,cfg.WSCLEAN_PATTERN,USE_SINGULARITY)
    ASTROPY_CONTAINER = gen.get_container(CONTAINER_PATH,cfg.ASTROPY_PATTERN,USE_SINGULARITY)


    # Get target information from project info json file

    with open('project_info.json') as f:
        project_info = json.load(f)

    target_ids = project_info['target_ids'] 
    target_names = project_info['target_names']
    target_ms = project_info['target_ms']
    master_ms = project_info['master_ms']

    zero_mask = '/scratch3/users/francesco.carotenuto/scratch1/reg_1543_ds9.reg'
    zero_mask_keyword = 'reg_1543_ds9'
    chanout_postpeel = cfg.WSC_CHANNELSOUT


    # Specify the directory to search
    directory_path = IMAGES
    keyword_postpeel = "postpeel-MFS-model.fits"
    print(IMAGES)
    # Initialize the variable to store the matching file name
    matching_file_postpeel = None

    # Debug: List all files in the directory
    if os.path.isdir(directory_path):
        #print("Files in directory:", os.listdir(directory_path))
        for file_name in os.listdir(directory_path):
        #print(f"Checking file: {file_name}\n")
            if keyword_postpeel in file_name:
                print(f"Match found: {file_name}")
                matching_file_postpeel = file_name
                break
    else:
        print(f"The directory '{directory_path}' does not exist.")
        exit(1)

    if matching_file_postpeel:
        print(f"File found: {matching_file_postpeel}")
        POSTPEEL_MODEL = '/'+matching_file_postpeel 
    else:
        print(f"No file containing '{keyword_postpeel}' found in the directory '{directory_path}'.")
        POSTPEEL_MODEL = "" 
    # Assign the result to a variable
     
    scan_pickle = 'scantimes_'+master_ms+'.p'
    scan_times = get_scan_times(scan_pickle)

    if not os.path.isdir('INTERVALS'):
        os.mkdir('INTERVALS')



    target_steps = []
    codes = []
    ii = 1
    stamp = gen.timenow()

    # ------------------------------------------------------------------------------
    #
    #  recipe definition
    #
    # ------------------------------------------------------------------------------
    for tt in range(0,len(target_ids)):

        targetname = target_names[tt]
        myms = target_ms[tt]
        master_ms = master_ms[tt]
        CAL_3GC_PEEL_REGION = cfg.CAL_3GC_PEEL_REGION
        skip = False
        

        if not o.isdir(myms):
            gen.print_spacer()
            print(gen.col('Target')+targetname)
            print(gen.col('MS')+'not found, skipping')
            skip = True

        if not skip:

            steps = []        
            filename_targetname = gen.scrub_target_name(targetname)


            code = gen.get_target_code(targetname)
            if code in codes:
                code += '_'+str(ii)
                ii += 1
            codes.append(code)

  

            # Image prefixes
            prepeel_img_prefix = IMAGES+'/img_'+myms+'_prepeel'
            postpeel_img_prefix = IMAGES+'/img_'+myms+'_postpeel'
            postpeel_mask_prefix = IMAGES+'/img_'+myms+'_postpeel-'+zero_mask_keyword
            #dir1_img_prefix = prepeel_img_prefix+'-'+CAL_3GC_PEEL_REGION.split('/')[-1].split('.')[0]

            # Target-specific kill file
            kill_file = SCRIPTS+'/kill_sti_jobs_'+filename_targetname+'.sh'

            print('Generating the following commands:\n')

            step = {}
            step['step'] = 0
            step['comment'] = 'Mask the target before uv-plane subtraction'
            step['dependency'] = None
            step['id'] = 'ZERO'+code
            syscall = CONTAINER_RUNNER+CUBICAL_CONTAINER+' ' if USE_SINGULARITY else ''
            syscall += 'python3 '+WATERHOLE+'/zero_mask_rectangle.py '
            syscall += '--region '+zero_mask+' '
            syscall += '--fitsfile ' + postpeel_img_prefix + ' '
            step['syscall'] = syscall
            steps.append(step)

            step = {}
            step['step'] = 1
            step['comment'] = 'Predict sky model visibilities without the source into MODEL_DATA column of '+myms
            step['dependency'] = 0
            step['id'] = 'WS3PR'+code
            step['slurm_config'] = cfg.SLURM_WSCLEAN_PREDICT
            step['pbs_config'] = cfg.PBS_WSCLEAN
            absmem = gen.absmem_helper(step,INFRASTRUCTURE,cfg.WSC_ABSMEM)
            syscall = CONTAINER_RUNNER+WSCLEAN_CONTAINER+' ' if USE_SINGULARITY else ''
            syscall += gen.generate_syscall_predict_postpeel(msname = myms, imgbase = postpeel_mask_prefix)
            step['syscall'] = syscall
            steps.append(step)

            step = {}
            step['step'] = 2
            step['comment'] = 'Subtract in the uvplane'
            step['dependency'] = 1
            step['id'] = 'UVSUB'+code
            syscall = 'singularity exec '+ASTROPY_CONTAINER+' '
            syscall += 'python3 tools/sum_MS_columns.py --src=MODEL_DATA --dest=CORRECTED_DATA --subtract '+myms
            step['syscall'] = syscall
            steps.append(step)
        
            step = {}
            step['step'] = 3
            step['comment'] = 'Make 8s timescale images'
            step['dependency'] = 2
            step['id'] = 'INT'+code
            for ss in scan_times:
                targetname = ss[0]
                scans = ss[1]
                intervals = ss[2]
            
                for i in range(0,len(scans)):
                    myms = glob.glob('*'+targetname+'.ms')
                    if len(myms) == 1:
                        myms = myms[0]
                        if os.path.isdir(myms):
                            opdir = 'INTERVALS/'+targetname+'_scan'+str(scans[i])
                            print(targetname)
                            if not os.path.isdir(opdir):
                                os.mkdir(opdir)

                            print('Target:    '+targetname)
                            print('Scans:     '+str(scans))
                            print('Intervals: '+str(intervals))

                            imgname = opdir+'/img_'+myms+'_modelsub'
                            code = 'intrvl'+str(scans[i])

                            syscall = 'singularity exec '+WSCLEAN_CONTAINER+' '
                            syscall += 'wsclean -intervals-out '+str(intervals[i])+' -interval 0 '+str(intervals[i])+' '
                            #syscall += 'wsclean '
                            syscall += '-log-time -field 0 -make-psf -size 10240 10240 -scale 1.1asec -use-wgridder -parallel-reordering 16 -parallel-gridding 16 -no-update-model-required '
                            syscall += '-parallel-deconvolution 2560 -gain 0.15 -mgain 0.9 -niter 0 -name '+imgname+' '
                            #syscall += '-channels-out 8 -fit-spectral-pol 4 -join-channels '
                            syscall += '-weight briggs -0.3 -data-column CORRECTED_DATA -padding 1.2 -auto-threshold 1.0 -auto-mask 6.0 '+myms
              
            step['syscall'] = syscall
            steps.append(step)
            
            target_steps.append((steps,kill_file,targetname))
            
            # ------------------------------------------------------------------------------
            #
            # Write the run file and kill file based on the recipe
            #
            # ------------------------------------------------------------------------------


    submit_file = 'submit_short_timescale_jobs.sh'

    f = open(submit_file,'w')
    f.write('#!/usr/bin/env bash\n')
    f.write('export SINGULARITY_BINDPATH='+cfg.BINDPATH+'\n')

    for content in target_steps:  
        steps = content[0]
        kill_file = content[1]
        targetname = content[2]
        id_list = []


        f.write('\n#---------------------------------------\n')
        f.write('# '+target_names[0])
        f.write('\n#---------------------------------------\n')

        for step in steps:

            step_id = step['id']
            id_list.append(step_id)
            if step['dependency'] is not None:
                dependency = steps[step['dependency']]['id']
            else:
                dependency = None
            syscall = step['syscall']
            if 'slurm_config' in step.keys():
                slurm_config = step['slurm_config']
            else:
                slurm_config = cfg.SLURM_DEFAULTS
            if 'pbs_config' in step.keys():
                pbs_config = step['pbs_config']
            else:
                pbs_config = cfg.PBS_DEFAULTS
            comment = step['comment']

            run_command = gen.job_handler(syscall = syscall,
                            jobname = step_id,
                            infrastructure = INFRASTRUCTURE,
                            dependency = dependency,
                            slurm_config = slurm_config,
                            pbs_config = pbs_config)


            f.write('\n# '+comment+'\n')
            f.write(run_command)

        if INFRASTRUCTURE != 'node':
            f.write('\n# Generate kill script for '+target_names[0]+'\n')
        if INFRASTRUCTURE == 'idia' or INFRASTRUCTURE == 'hippo':
            kill = 'echo "scancel "$'+'" "$'.join(id_list)+' > '+kill_file+'\n'
            f.write(kill)
        elif INFRASTRUCTURE == 'chpc':
            kill = 'echo "qdel "$'+'" "$'.join(id_list)+' > '+kill_file+'\n'
            f.write(kill)

        
    f.close()

    gen.make_executable(submit_file)

    gen.print_spacer()
    print(gen.col('Run file')+submit_file)
    gen.print_spacer()

    # ------------------------------------------------------------------------------



if __name__ == "__main__":


    main()
