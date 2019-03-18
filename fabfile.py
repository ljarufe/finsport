from fabric import Connection, Config, task

from common.print_color import ColorPrint as _


# TODO: Credentials will be saved on the .env file
def get_connection():
    sudo_pass = 'Chuchupe7'
    config = Config(overrides={'sudo': {'password': sudo_pass}})
    return Connection(
        host='51.77.156.101',
        user='ljarufe',
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
