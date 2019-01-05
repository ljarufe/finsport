# Finsport
(Tested on 16.04.1-Ubuntu or greater)

## Installation
There is the complete list of packages required by the project
```
$ sudo apt-get install build-essential python-dev python python-virtualenv python-pip libjpeg8 libjpeg62-dev 
```

### Postgres

```
$ sudo su postgres -c psql

postgres$ create user finsport with password 'finsport';

postgres$ create database finsport owner finsport encoding 'UTF8' LC_COLLATE = 'en_US.UTF-8' LC_CTYPE = 'en_US.UTF-8';
```

#### Only for local purposes to use fabric

```
postgres$ alter user finsport with superuser;
```

Edit the `/etc/postgresql/9.5/main/pg_hba.conf` file as root user:

```
local all postgres trust

local all all trust
```

Restart the service

```
$ /etc/init.d/postgresql restart
```

## Configure the project
### Create a virtualenv

```
$ mkdir finsport
$ cd finsport
$ virtualenv -p python3 env
```

This command will create a new folder with the name env
### Create a logs, selenium and scrappy directories
Create logs directory
```
$ mkdir logs
$ cd ..
$ mkdir db_backup
$ cd ..
$ touch logs/messages.log
$ mkdir selenium-data
$ cd ..
$ mkdir spide-data 
```

### Move a chromedriver
```
 $ cd selenium-data
 ```
Inside this folder you hace to move the chrome driver necesary for selenium
### Clone the project

First verify your SSH Keys on github configuration `https://github.com/settings/keys`
then if you dont have a key that points to your computer follow this tutorial 
`https://help.github.com/articles/connecting-to-github-with-ssh/`

In a server in case you need to add the public key to the deployements keys in the project 
`https://github.com/ljarufe/finsport/settings/keys`

now you can clone your repository using ssh

```
git@github.com:ljarufe/finsport.git
```

### Activate your enviroment
Inside the  folder run the following command

```
$ source ../env/bin/activate
```

After this you will see the virtualenv name in your promp. i.e.:

```
(env) $
```

### Install requirements
```

(env)$ pip install -r requirements.txt
```


#### .env file
You have to add .env file with your local variables

In order to check that everything is ok. Run this command:

```
($project_name$) $ ./manage.py check
```

