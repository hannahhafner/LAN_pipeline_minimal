#!/usr/bin/env python3
"""
Generates and submits individual sbatch job for generating simulated data for a given model, and/or for training neural network on simulated data.
"""
import argparse
from argparse import RawDescriptionHelpFormatter
from pathlib import Path
import logging
import subprocess
import yaml
import textwrap

# SBATCH template
SBATCH_TEMPLATE = """#!/bin/bash

# specifies sbatch resources needed for the job

#SBATCH --mem={mem}
#SBATCH -J {job_name}
#SBATCH --time={time}
#SBATCH --output={output}
#SBATCH --error={error}
#SBATCH --array=1-{array_size}

# Your commands here
{environment}

uv run {command}
"""

def create_command(command_name: str, **params: dict):
    """
    Creates a full CLI command to be run using the SBATCH script.

    Parameters:
        command_name (string): name of the Python file you are going to run (generate.py or jaxtrain.py)
        params (dictionary): dictionary of parameters to be used with the Python file

    Returns:
        command (string): full CLI command, with the script to be run, and all parameters

    """
    command = f"{command_name} "
    command += " ".join([f"--{key} {value}" for key, value in params.items()])
    
    return command

def create_sbatch_script(
    job_name="job",
    output="output.txt",
    error="error.txt",
    time="01:00:00",
    mem="4G",
    command="",
    environment="",
    array_size=1
):
    """
    Creates a SBATCH script using the SBATCH template.

    Parameters:
        job_name (string): Name for SBATCH job
        outputs (string): Name for output file after running SBATCH job
        error (string): Name for the error file after running SBATCH job
        time (string): Time limit for job
        mem (string): Amount of memory in GB to be used with SBATCH job
        command (string): Python command(s) to run after setting up all SBATCH metadata
        environment (string): Additional metadata that includes commands to create the appropriate environment for generate or jaxtrain

    Returns:
        sbatch_script (sbatch_template): SBATCH script with metadata used for running SBATCH jobs

    """

    sbatch_script = SBATCH_TEMPLATE.format(
        mem=mem,
        job_name=job_name,
        time=time,
        output=output,
        error=error,
        command=command,
        environment=environment,
        array_size=array_size
    )
    return sbatch_script

def write_sbatch(script, sbatch_script):
    """
    Adds SBATCH metadata to .sh script

    Parameters:
        script (.sh file): .sh file that will be turned into an SBATCH script
        sbatch_script (string): output from the create_sbatch_script function with SBATCH metadata

    Returns:
        None.
    """
    with open(script, "w") as f:
        f.write(sbatch_script)

def submit_sbatch(script, logger):
    """
    Submits SBATCH .sh file to OSCAR.

    Parameters:
        script (SBATCH .sh): script with SBATCH metadata added after running write_sbatch
        logger (Logger): logger from file
    """
    try:
        result = subprocess.run(["sbatch", script], capture_output=True, text=True)
        logger.info(result.stdout)
        if result.stderr:
            logger.error(result.stderr)
    except Exception as e:
        logger.error(f"Failed to submit job: {e}")

def get_basic_config_from_yaml(
    yaml_config_path: str | Path
):
    """
    Load the basic configuration from a YAML file. Modified from the generate.py file
    
    Parameters:
        yaml_config_path (string or Path): path to the .yaml config file for use with generate.py

    Returns:
        basic_config (dictionary?): basic configuration dictionary, taken from the config.yaml file
    
    """
    basic_config = yaml.safe_load(open(yaml_config_path, "rb"))
    return basic_config

def get_environment_setup(args: argparse.Namespace):
    """
    Sets up environment for running generate or jaxtrain if the --make-env argument is sued

    Parameters:
        args (argparse.Namespace): Parsed arguments used for generate or jaxtrain
    """
    if args.make_env:

        if args.command == "generate":

            environment = textwrap.dedent("""
            module load python
            module load gcc
            if [ ! -d "ssm-simulators" ]; then
                git clone https://github.com/lnccbrown/ssm-simulators.git -b add-generate-to-release-0.8.3
            fi               
            cd ssm-simulators
            git checkout add-generate-to-release-0.8.3
            uv sync""")

        elif args.command == "jaxtrain":

            environment = textwrap.dedent("""
            module load python
            module load gcc
            cd LAN_pipeline_minimal
            uv sync""")
            
    else:
        environment=""

    return environment
    
def get_parameters_setup(args: argparse.Namespace):
    """
    Creates parameter dictionary for use with generate or jaxtrain

    Parameters:
        args (argparse.Namespace): Parsed arguments used for generate or jaxtrain
    """
    
    # Ensuring that config path is an absolute, not a relative path
    args.config_path = Path.resolve(args.config_path)

    params = {
        "config-path": args.config_path.resolve(),
        "log-level": args.log_level
    }

    if args.command == "generate":
        
        params["output"] = args.output_path.resolve()

    elif args.command == "jaxtrain":

        params.update(
            {
                "networks-path-base": args.output_path.resolve(),
                "training-data-folder": args.training_data_folder.resolve(),
                "network-id": args.network_id,
                "dl-workers": args.dl_workers,
            }
        )

    return params

def main():

    # Setting up argument parsing 

    description = __doc__ # docstring for gen_sbatch
    prog = "gen_sbatch" # program name

    epilog = (
        f"Example:\n    {prog} generate --config-path path/to/config.yaml --output-path path/to/output/folder --array-size 1 --time 24:00:00 --sh-only --make-env --log-level INFO\n"
        f"    {prog} jaxtrain --config-path path/to/config.yaml --output-path path/to/trained_network_output --training-data-folder path/to/training_data --network-id 0 --dl-workers 4 --time 00:10:00 --sh-only --make-env --log-level INFO\n" # examples for generate and jaxtrain scripts
    )
    parser = argparse.ArgumentParser(
        description = description,
        prog = prog,
        epilog = epilog,
        formatter_class=RawDescriptionHelpFormatter 
    )

    # Only the config-path and --output-path arguments, since these should be the first two arguments for generate and jaxtrain
    parent_parser_config = argparse.ArgumentParser(add_help=False)
    parent_parser_config.add_argument(
        "--config-path",
        default="dump",
        help="Path to configuration .yaml file for running commands (default: 'dump')",
        type=Path,
        required=True
    )
    parent_parser_config.add_argument(
        "--output-path",
        default="dump",
        help="Path to output folder for simulated data (generate) or trained neural network (jaxtrain)",
        type=Path,
        required=True
    )
    
    # Common metadata arguments for both generate and jaxtrain
    parent_parser_metadata = argparse.ArgumentParser(add_help=False)
    parent_parser_metadata.add_argument(
        "--time", 
        help="Wall time limit for each job (default: 24:00:00)", 
        default="24:00:00"
    )
    parent_parser_metadata.add_argument(
        "--sh-only",
        action="store_true",
        help="Generate the sbatch script without submitting the job",
    )
    parent_parser_metadata.add_argument(
        "--make-env",
        action="store_true",
        help="Create correct environment to run generate or jaxtrain in the SBATCH script",
    )
    parent_parser_metadata.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the log level (default=WARNING)",
    )

    # Subparsers for arguments specific to generate and jaxtrain
    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        required=True,
    )
    # Generate args
    generate_parser = subparsers.add_parser(
        "generate", help="Generates simulated data from model parameters", 
        parents=[parent_parser_config]
    )
    generate_parser.add_argument(
        "--array-size", type=int, default=1, help="Size of the job array (default: 1)"
    )

    # Jaxtrain args
    jaxtrain_parser = subparsers.add_parser(
        "jaxtrain", help = "Trains a neural network using simulated data", 
        parents=[parent_parser_config]
    )
    jaxtrain_parser.add_argument(
        "--training-data-folder",
        help="Path to folder with data to train the neural network on",
        type=Path,
        required=True
    )
    jaxtrain_parser.add_argument(
        "--network-id",
        type=int,
        help="Id for the neural network to train (default=0).",
        default=0,
    )
    jaxtrain_parser.add_argument(
        "--dl-workers",
        type=int,
        help="Number of cores to use with the dataloader class (default=1)",
        default=0,
        required=True
    )

    # Manually adding metadata parent arguments to the subparsers so the order is correct
    for action in parent_parser_metadata._actions:
        if isinstance(action, argparse._HelpAction):
            continue  # skip help, already there
        jaxtrain_parser._add_action(action)
        generate_parser._add_action(action)

    args = parser.parse_args()

    # Setting up logging
    logger = logging.getLogger(__file__)
    logging.basicConfig(
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, args.log_level)
    )

    if args.command == "generate":

        # target folder for generate
        target = args.output_path.resolve()

        # Add correct environment to SBATCH file
        environment=get_environment_setup(args)

        # get parameters for command from the arguments parser
        params = get_parameters_setup(args)

        # Create command
        command = create_command("generate", **params)
        logger.info(f"Generated command: {command}")

        # Get configuration file metadata 
        bc = get_basic_config_from_yaml(params["config-path"])
        
        # Use information from config file to name job and sbatch script
        job_name = f"{bc['MODEL']}_generate_sbatch" 
        script = f"{bc['MODEL']}_generate_sbatch.sh"

        # Create SBATCH metadata
        sbatch_script = create_sbatch_script(
                job_name=job_name,
                output=f"{job_name}.out",
                error=f"{job_name}.err",
                time=args.time,
                command=command,
                mem="16G",
                environment=environment,
                array_size=args.array_size
        )

        # Run sbatch
        write_sbatch(script, sbatch_script)

        # Generate sbatch only, do not submit job
        if args.sh_only:
            logger.info(f"Generated sbatch script: {script}")
            return
        
        # Make output folder for simulated data
        target.mkdir(exist_ok=True, parents=True)
        logger.info(f"Simulated data output folder: {target}")

        # Submits job
        submit_sbatch(script, logger)
        logger.info(F"Job submitted successfully")

    elif args.command == "jaxtrain":
  
        # target folder for jaxtrain
        target = args.output_path.resolve()

        # Set up environment
        environment=get_environment_setup(args)

        # Get parameters from the parsed arguments
        params = get_parameters_setup(args)

        # Create command
        command = create_command("jaxtrain", **params)
        logger.info(f"Generated command: {command}")

        # Get metadata about job from the configuration file
        bc = get_basic_config_from_yaml(params["config-path"])

        # Use info from the configuration file to name job and .sh script
        job_name = f"{bc['MODEL']}_jaxtrain_sbatch" #TODO: need to figure out how to get better job names and script names later
        script = f"{bc['MODEL']}_jaxtrain_sbatch.sh"

        # Create SBATCH metadata
        sbatch_script = create_sbatch_script(
                job_name=job_name,
                output=f"{job_name}.out",
                error=f"{job_name}.err",
                time=args.time,
                command=command,
                mem="16G",
                environment=environment
            )

        # Run sbatch
        write_sbatch(script, sbatch_script)

        # Generate sbatch only, do not submit job
        if args.sh_only:
            logger.info(f"Generated sbatch script: {script}")
            return
        
        # Make output folder for trained network
        target.mkdir(exist_ok=True, parents=True)
        logger.info(f"Trained networks output folder: {target}")

        # Submits job
        submit_sbatch(script, logger)

# Main
if __name__ == "__main__":
    main()

