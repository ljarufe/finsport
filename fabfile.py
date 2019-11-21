from fabric import Connection, Config, task

from common.print_color import ColorPrint as _

import environ

root = environ.Path(__file__) - 2
env = environ.Env()
environ.Env.read_env('%s/.env' % str(root))


def get_connection():
    sudo_pass = env('HOST_PASS')
    config = Config(overrides={'sudo': {'password': sudo_pass}})
    return Connection(
        host=env('HOST_IP'),
        user=env('HOST_USER'),
        connect_kwargs={'key_filename': '/home/luis/.ssh/id_rsa'},
        config=config,
    )


@task
def deploy(c):
    c = get_connection()
    with c.cd('/home/ljarufe/Projects/finsport/finsport'):
        _.print_info("Borrando archivos pyc")
        c.run('find . -iname "*.pyc" -delete')
        _.print_info("Actualizando repositorio")
        c.run('export GIT_SSL_NO_VERIFY=1')
        c.run('git pull')
        with c.prefix('source ../bin/activate'):
            _.print_info("Instalando paquetes")
            c.run('pip install -r requirements.txt')
            _.print_info("Corriendo migraciones")
            c.run('python manage.py migrate --noinput')
            _.print_info("Colectando archivos estaticos")
            c.run('python manage.py collectstatic --noinput')
    _.print_info("Reiniciando uwsgi")
    c.sudo('/etc/init.d/uwsgi restart')
    _.print_pass("Listo!")


@task
def deployf(c):
    c = get_connection()
    with c.cd('/home/ljarufe/Projects/finsport-frontend'):
        _.print_info("Actualizando repositorio")
        c.run('export GIT_SSL_NO_VERIFY=1')
        c.run('git pull')
        _.print_info("Instalando paquetes")
        c.run('npm install')
        _.print_info("Contruyendo...")
        c.run('npm run build')
    _.print_pass("Listo!")