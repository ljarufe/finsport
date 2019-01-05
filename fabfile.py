import fabutils

from django.conf import settings

from fabric.contrib import django
from fabric.api import prefix, run, env

django.settings_module('finsport.settings')


fabutils.autodiscover_environments(settings)


class VirtualenvMixinCustom(fabutils.VirtualenvMixin):

    def fab_run_env(self, *args, **kwargs):
        """
        Runs commands using virtualenv
        """

        with prefix('source %s/../env/bin/activate' % env.core_dir):
            return run(*args, **kwargs)


class Deploy(fabutils.SupervisorMixin, fabutils.UwsgiMixin,
             fabutils.VirtualenvMixin, fabutils.Deployment):

    """
    Base deployment class, do not use it directly in the commands
    """

    database_handler = fabutils.PostgresqlDatabaseBackup


class PostgresqlDatabaseOperations(fabutils.LocalDatabaseOperations):

    db_backup_handler_class = fabutils.PostgresqlDatabaseBackup
    db_restore_handler_class = fabutils.PostgresqlDatabaseRestore


fabutils.register_class(Deploy, settings)
fabutils.register_class(PostgresqlDatabaseOperations, settings)
fabutils.register_class(fabutils.RemoteDatabaseOperations, settings)
