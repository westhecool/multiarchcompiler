import json
import subprocess
import argparse
import sys
import platform
import os
import random
import string
import tempfile
import time
import atexit


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


options = {
        "volumes": {
            "type": list,
            "required": True,
            "default": "(none)",
            "help": "should be an list of strings following docker volume format"
        },
        "dockerargs": {
            "type": str,
            "required": False,
            "default": "",
            "help": "additional arguments to pass to docker"
        },
        "arches": {
            "type": list,
            "required": True,
            "default": "(none)",
            "help": "an list of strings containing the arches you want to compile for"
        },
        "image": {
            "type": str,
            "required": True,
            "default": "(none)",
            "help": "the image to use"
        },
        "containername": {
            "type": str,
            "required": False,
            "default": "{random}-{arch}",
            "help": "the name format for naming the docker containers"
        },
        "build": {
            "type": str,
            "required": True,
            "default": "(none)",
            "help": "path to the script to compile your program"
        },
        "removecontainers": {
            "type": bool,
            "required": False,
            "default": True,
            "help": "remove the containers after the compilation has completed"
        }
}

parser = argparse.ArgumentParser(
    prog='Multi Arch Compiler',
    description='A script for using QEMU and docker to build for multiple arches on the same system',
    epilog='see https://site.com for more information')
parser.add_argument('-c', '--configfile', help='path to a config file')
parser.add_argument('-l', '--logfile',
                    help='path to a file to save the log to')
parser.add_argument('-v', '--verbose', action='store_true',
                    help='explain in more detail what this script is doing')
parser.add_argument('-V', '--version', action='store_true',
                    help='print version and exit')
parser.add_argument('--ignorewarnings', action='store_true',
                    help='override warnings')
parser.add_argument('--confighelp', action='store_true',
                    help='prints the guide for making a configuration file')
args = parser.parse_args()

if args.version:
    print('Multi Arch Compiler v1.0')
    exit()

if args.confighelp:
    print('The config should be a valid json file containing information on what to do')
    print('')
    print('The following variables are available in the following properties: containername, image, dockerargs, build:')
    print('')
    print('"{arch}" - the arch that it is currently compiling for')
    print('"{random}" - a random string of 20 characters')
    print('')
    print('Config file properties:')
    print('')
    for key in options:
        print(f'{key}:')
        print('    Type: {r}'.format(r=str(options[key]['type'].__name__)))
        print('    Required: {r}'.format(r=str(options[key]['required'])))
        print('    Default: {r}'.format(r=str(options[key]['default'])))
        print('    Description: {r}'.format(r=str(options[key]['help'])))
        print('')
    exit()

if not args.configfile:
    eprint('error: the following arguments are required: -c/--configfile')
    exit(1)

LOGFILE = False
try:
    LOGFILE = open(args.logfile, mode='a')
except:
    eprint('not logging to a file')


def exit_handler():
    if LOGFILE:
        LOGFILE.close()


atexit.register(exit_handler)

if LOGFILE:
    LOGFILE.write(f'\n\nnew log {time.ctime()}\n\n')


def errorLogPrint(*args, **kwargs):
    if LOGFILE:
        print(*args, file=LOGFILE, **kwargs)
    eprint(*args, **kwargs)


def logPrint(*args, **kwargs):
    if LOGFILE:
        print(*args, file=LOGFILE, **kwargs)
    print(*args, **kwargs)


def randomstr(length):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))


def execCommand(command, **args2):
    if args.verbose:
        logPrint('run command: ' + command)
    return subprocess.run(command, **args2)


def formatStringArch(arch, string):
    return string.replace('{arch}', arch).replace('{random}', randomstr(20))


def validateConfig(config):
    errors = ''
    for key in options:
        try:
            config[key]
            if not type(config[key]) == options[key]['type']:
                errors += 'The option "' + key + '" is type "' + \
                    type(config[key]).__name__ + '" but it should be of type "' + \
                    options[key]['type'].__name__ + '"\n'
        except KeyError:
            if options[key]['required']:
                errors += 'The required option "' + key + '" is not found\n'
            else:
                config[key] = options[key]['default']
    if len(errors):
        errorLogPrint(
            'The following errors were found while attempting to parse the config file:\n' + errors)
        exit(1)
    return config


if args.verbose:
    logPrint('testing platform...')
platformok = platform.architecture()[0] == '64bit' and (
    platform.system() == 'Linux' or platform.system() == 'Darwin')

if not platformok and not args.ignorewarnings:
    errorLogPrint(
        'This script only works on 64bit Linux or Darwin. exiting...\nuse --ignorewarnings to override this')
    exit(1)

if args.verbose:
    logPrint('testing if the user id root...')
userok = False
try:
    userok = os.getuid() == 0
except:
    errorLogPrint('os.getuid() doesn\'t appear to exist')

if not userok and not args.ignorewarnings:
    errorLogPrint(
        'detect current user is not root, must be run as root. exiting...\nuse --ignorewarnings to override this')
    exit(1)

if args.verbose:
    logPrint('testing for docker...')
dockerok = subprocess.run('docker --version', shell=True).returncode == 0

if not dockerok and not args.ignorewarnings:
    errorLogPrint(
        'docker not found. exiting...\nuse --ignorewarnings to override this')
    exit(1)

if args.verbose:
    logPrint('opening config file...')

try:
    f = open(args.configfile)
except FileNotFoundError:
    errorLogPrint('cannot open the config file!')
    exit(1)

try:
    config = json.loads(f.read())
except json.decoder.JSONDecodeError:
    errorLogPrint(
        'failed to parse the json, is the config file a valid json file?')
    exit(1)

config = validateConfig(config)

if args.verbose:
    logPrint('config file valid')

logPrint('setting up qemu-user-static...')
QEMUoutput = execCommand('docker run --rm --privileged multiarch/qemu-user-static --reset -p yes', shell=True, capture_output=True, text=True)
logPrint('[qemu-user-static output]: ' + '\n[qemu-user-static output]: '.join(QEMUoutput.stdout.split('\n')))

volumes = ''

for volume in config['volumes']:
    volumes += f'-v "{volume}"'

for arch in config['arches']:
    with tempfile.TemporaryDirectory() as tmpdirname:
        logPrint('building for ' + arch)
        try:
            file = open(formatStringArch(arch, config['build']))
        except FileNotFoundError:
            errorLogPrint('cannot find build script "' +
                          formatStringArch(arch, config['build']) + '"')
            exit(1)
        file2 = open(tmpdirname + '/build.sh', mode='w')
        file2.write(file.read())
        file2.close()
        file.close()
        rm = ''
        if config['removecontainers']:
            rm = '--rm'
        r = execCommand('docker run {rm} -v "{tmpdir}:/buildcommand" --name "{name}" {volumes} {dockerargs} "{image}" bash /buildcommand/build.sh 2>&1'.format(
            name=formatStringArch(arch, config['containername']),
            image=formatStringArch(arch, config['image']),
            tmpdir=tmpdirname,
            dockerargs=formatStringArch(arch, config['dockerargs']),
            volumes=volumes,
            rm=rm), shell=True, capture_output=True, text=True)
        logPrint('[docker output]: ' + '\n[docker output]: '.join(r.stdout.split('\n')))