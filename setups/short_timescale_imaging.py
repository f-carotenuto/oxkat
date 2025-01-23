


#!/usr/bin/env python
# ian.heywood@physics.ox.ac.uk


import glob
import json
import os.path as o
import sys
import subprocess
sys.path.append(o.abspath(o.join(o.dirname(sys.modules[__name__].__file__), "..")))


from oxkat import generate_jobs as gen
from oxkat import config as cfg


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


    # Get target information from project info json file

    with open('project_info.json') as f:
        project_info = json.load(f)

    target_ids = project_info['target_ids'] 
    target_names = project_info['target_names']
    target_ms = project_info['target_ms']
    working_ms = project_info['working_ms']

    zero_mask = '/scratch3/users/francesco.carotenuto/scratch1/reg_1543_ds9.reg'
    scantimes = 'scantimes_'+work_ms+'.p'
    chanout_postpeel = cfg.CAL_3GC_PEEL_NCHAN/4


    # Specify the directory to search
    directory_path = IMAGES
    keyword_postpeel = "postpeel-MFS-model.fits"

    # Initialize the variable to store the matching file name
    matching_file_postpeel = None

    # Iterate through the files in the directory
    for file_name_postpeel in os.listdir(directory_path):
        file_path = os.path.join(directory_path, file_name_postpeel)
        if os.path.isfile(file_path) and keyword_postpeel in file_name_postpeel:
            matching_file_postpeel = file_name_postpeel
        break

    if matching_file_postpeel:
        print(f"File found: {matching_file_postpeel}")
    else:
        print(f"No file containing '{keyword_postpeel}' found in the directory.")

    # Assign the result to a variable
    file_name_postpeel = matching_file_postpeel  

    POSTPEEL_MODEL = file_name_postpeel

    # ------------------------------------------------------------------------------
    #
    #  recipe definition
    #
    # ------------------------------------------------------------------------------
    for tt in range(0,len(target_ids)):

        targetname = target_names[tt]
        myms = target_ms[tt]
        work_ms = working_ms[tt]
        CAL_3GC_PEEL_REGION = cfg.CAL_3GC_PEEL_REGION
        skip = False

        target_steps = []
        codes = []
        ii = 1
        stamp = gen.timenow()


        # Image prefixes
        prepeel_img_prefix = IMAGES+'/img_'+myms+'_prepeel'
        postpeel_img_prefix = IMAGES+'/img_'+myms+'_postpeel'
        postpeel_mask_prefix = IMAGES+'/img_'+myms+'_postpeel'+zero_mask
        #dir1_img_prefix = prepeel_img_prefix+'-'+CAL_3GC_PEEL_REGION.split('/')[-1].split('.')[0]

        # Target-specific kill file
        kill_file = SCRIPTS+'/kill_sti_jobs_'+filename_targetname+'.sh'


        step = {}
        step['step'] = 0
        step['comment'] = 'Mask the target before uv-plane subtraction'
        step['dependency'] = None
        step['id'] = 'ZERO'+code
        syscall = CONTAINER_RUNNER+CUBICAL_CONTAINER+' ' if USE_SINGULARITY else ''
        syscall += 'python3 '+WATERHOLE+'/zero_mask_rectangle.py '
        syscall += '--region '+zero_mask+' '
        syscall += '--fitsfile'+IMAGES+POSTPEEL_MODEL+''
        step['syscall'] = syscall
        steps.append(step)

       

        step = {}
        step['step'] = 1
        step['comment'] = 'Predict sky model visibilities without the source into MODEL_DATA column of '+myms
        step['dependency'] = 0
        step['id'] = 'WS3PR'+code
        step['slurm_config'] = cfg.SLURM_WSCLEAN
        step['pbs_config'] = cfg.PBS_WSCLEAN
        absmem = gen.absmem_helper(step,INFRASTRUCTURE,cfg.WSC_ABSMEM)
        syscall = CONTAINER_RUNNER+WSCLEAN_CONTAINER+' ' if USE_SINGULARITY else ''
        syscall += gen.generate_syscall_predict(msname = myms, imgbase = postpeel_mask_prefix, chanout = chanout_postpeel, absmem = absmem)
        step['syscall'] = syscall
        steps.append(step)

        step = {}
        step['step'] = 2
        step['comment'] = 'Subtract in the uvplane'
        step['dependency'] = 1
        step['id'] = 'UVSUB'+code
        syscall = CONTAINER_RUNNER+CUBICAL_CONTAINER+' ' if USE_SINGULARITY else ''
        syscall += 'python3 '+WATERHOLE+'/setup_uvsub.py '+myms+' '
        step['syscall'] = syscall
        steps.append(step)
    
        step = {}
        step['step'] = 3
        step['comment'] = 'Make 8s timescale images'
        step['dependency'] = 2
        step['id'] = 'INT'+code
        syscall = CONTAINER_RUNNER+CUBICAL_CONTAINER+' ' if USE_SINGULARITY else ''
        syscall += 'python3 '+WATERHOLE+'/setup_intervals.py '+scantimes+' '
        step['syscall'] = syscall
        steps.append(step)
 


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
        f.write('# '+targetname)
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
            f.write('\n# Generate kill script for '+targetname+'\n')
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