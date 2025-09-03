# Finsport

## Docker
Install Docker in your local machinne.

## Clone the project
First verify your SSH Keys on github configuration `https://github.com/settings/keys`
then if you dont have a key that points to your computer follow this tutorial
`https://help.github.com/articles/connecting-to-github-with-ssh/`

In a server in case you need to add the public key to the deployements keys in the project
`https://github.com/ljarufe/finsport/settings/keys`

now you can clone your repository using ssh

```
git@github.com:ljarufe/finsport.git
```

#### .env file
You have to add .env file with your local variables using .env.dist as a template

In order to check that everything is ok. Run this command:

```
($project_name$) $ ./manage.py check
```

## Database load
```
$ docker compose up
```

To load the database backup comment the migrate RUN in Dockerfile and follow this steps:
```
$ docker cp finsport.sql <postgresql_container_name>:/docker-entrypoint-initdb.d/finsport.sql
$ docker exec -it <postgresql_container_name> psql -U finsport -d finsport -f /docker-entrypoint-initdb.d/finsport.sql
```

### Share a database
To make a backup
```
pg_dump -U <user> <database> > nombre_db.sql
```

To load the backup
```
psql -U <user> <database> < nombre_db.sql
```

### Serve REST for Reactjs
```
./manage.py runserver 0.0.0.0:8000
```

### Format
Run pylint in the entire project
```
python -m pylint .
```

Run black to format automaticaly

```
python -m black --target-version=py37 .
```
