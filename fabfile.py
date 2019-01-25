from __future__ import with_statement
import os
import sys
from fabric.api import *
from fabric.colors import green
from fabric.contrib import django
django.settings_module('settings')

PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, '..'))


# TODO: Credentials will be saved on the .env file
def prod():
    env.hosts = ['ljarufe@51.77.156.101']
    env.password = 'Chuchupe7'
    env.core_dir = '/home/ljarufe/Projects/finsport/finsport'
    env.db_name = "finsport"
    env.db_user = "finsport"
    env.db_pass = "finsport"


def deploy():
    with cd(env.core_dir):
        update_repo()
        install_requirements()
        update_database()
        clear_pyc_files()
        collectstatic()
    restart_uwsgi()


def run_env(cmd):
    with prefix('source %s/../bin/activate' % env.core_dir):
        run(cmd)


def update_repo():
    print(green("Updating repo"))
    run('export GIT_SSL_NO_VERIFY=1')
    run('git pull')


def install_requirements():
    run_env('pip install -r requirements.txt')


def update_database():
    print(green("Updating database"))
    run_env('python manage.py migrate --noinput')


def clear_pyc_files():
    print(green("Deleting pyc files"))
    run('cd %s && find . -iname "*.pyc" -delete' % env.core_dir)


def collectstatic():
    print(green("Collecting static files from apps"))
    run_env('python manage.py collectstatic --noinput')


def restart_uwsgi():
    sudo("/etc/init.d/uwsgi restart")
