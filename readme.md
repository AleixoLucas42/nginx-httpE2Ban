# httpE2Ban for Nginx
This is an simple nginx add-on that block connections based on http status. I know that exists a lot of tools like this but I made for my own to be lightier and also, to be as an "first shield" for applications running behind Nginx. The configuration should be simple and mainly you should be using Nginx on a docker container, but also works for a common Nginx instalation.

## Validation
I've tested on these configurations.
| Docker version | Operational system | Test result        |
|----------------| -------------------|--------------------|
|    27.1.2      |   Fedora 39        | :white_check_mark: |

## How it works
You have to set an configuration policy, that says how much http code an client can have over time. For example:
```json
{
    "404": {"limit": 10, "window": 60},
    "403": {"limit": 5, "window": 60},
    "401": {"limit": 5, "window": 60}
}
```
In this example, on first statement, a client can throw only ten 404 http errors over 60 seconds; on second, only five 403 http error over 60 seconds and so on. Simple, right?

On your `nginx.conf` you'll have to include the [ban file](banned.conf) and a block condition, for exampleS:
```lua
...
include /etc/nginx/conf.d/banned.conf;
server {
    if ($blocked) {
        return 444; # You can choose whatever http status you want
    }
}
# you can also redirect for an custom error page.
...
```
Finally, the httpE2Ban need to access the Nginx access.log (assuming you're using nginx default log pattern). **With this policy and ban file, the httpE2Ban is going to listen the access.log, populate the ban file and send an reload signal to Nginx.**

## Setup
For setup you have to do **three steps:**

- Configure an [json policy file](policy.json).
- Nginx configuration
  - Configure your nginx to include the [ban file](banned.conf). Here you can find an example on first line of [nginx.conf](nginx.conf).
  - Configure an condition in your server config to block IPs based on a map in the ban file. Here you can find an example on line 6 to 8 on [nginx.conf](nginx.conf).
- Give access in nginx access logs to httpE2Ban using environment variable.

## Running [docker compose](docker-compose.yaml) example (poc)
- Download repository
- On repository root, run `docker compose up`
- Access site example on http://localhost:8080
- Access error page example on http://localhost:8080/401
- Access error page more than 5 times and you should be blocked
- Now you can not access no any page on this server.
- Check the [ban file](banned.conf) and your IP should be there next to an epoch timestamp.

### Docker compose explained
Here is an example on a more [complex cenario](https://github.com/AleixoLucas42/homelab/tree/main/proxmox-vms/fedora-server/swarm/nginx).
```yaml
name: nginx-httpE2Ban
services:
  nginx:
    container_name: nginx-container-name
    volumes:
      - ./site-example:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./access.log:/var/log/nginx/access.log #¹
      - ./banned.conf:/etc/nginx/conf.d/banned.conf:ro #²
    image: nginx
    ports:
      - 8080:80
    environment:
      - NGINX_PORT=80
      - TZ=America/Sao_Paulo #³
  nginx_httpe2ban:
    container_name: httpe2ban
    volumes:
      - ./access.log:/httpe2ban/access.log:ro #¹
      - ./banned.conf:/httpe2ban/banned.conf:rw #²
      - /var/run/docker.sock:/var/run/docker.sock #£
      - /usr/bin/docker:/usr/bin/docker #£
    image: aleixolucas/nginx-httpe2ban #£
    environment:
      TZ: "America/Sao_Paulo" #³
      POLICY: >
        {
            "404": {"limit": 10, "window": 60},
            "403": {"limit": 5, "window": 60},
            "401": {"limit": 5, "window": 60}
        }
    depends_on:
        - nginx
```
1. Mapping the nginx access.log in directory to httpE2Ban have access.
2. Mapping ban file inside Nginx container as read only.
3. This is the timezone of your location, for better time handling.
4. £. This is the way I gave docker cli to httpE2Ban. You have to do the same if you have no other way to access your Nginx, to avoid this, you can use the environment variable `RELOAD_NGINX_CUSTOM_CMD` so httpE2Ban can use this command to access the nginx and send nginx reload. Check if your docker socked and binary are in the same path as docker compose if you have any trouble.

## Run without docker
To run withou docker, you should have python3.9 installed.
- Create virtual environment
> python3 -m venv .venv
- Activate venv
> source .venv/bin/activate # Linux

> C:\ .venv\Scripts\activate.bat # Window
- Install packages on virtual environment
> pip install -r requirements.txt
- Create the banned file
```sh
# Should have this pattern when first create
echo "map $remote_addr $blocked {
    default 0;

}" > $HOME/nginx-httpE2Ban/banned.conf
```
- Set the environment variables. Example:
```sh
export RELOAD_NGINX_CUSTOM_CMD="ssh user@123.456.789.0 'nginx -s reload'"
export NGINX_LOG_PATH="/var/log/nginx/access.log"
export POLICY_FILE="$HOME/nginx-httpE2Ban/policy.json"
export BANNED_CONF_FILE="$HOME/nginx-httpE2Ban/banned.conf"
# read the documentation below if necessary.
```
- Finally, run the [main.py](main.py) file
> python3 main.py

## Environment variables
| Name | Example | Required |Description |
|-------------------| ------- | --------------------------------|------------------|
| TZ | America/Sao_Paulo | No | Your Timezone. If not set, is going to use America/Sao_Paulo. |
| NGINX_CONTAINER_NAME | nginx-prod | No | Nginx container name. If not set, httpE2Ban will restart the first container that is running Nginx image |
| RELOAD_NGINX_CUSTOM_CMD | ssh user@123.456.789.0 "nginx -s reload" | No | Custom command to restart Nginx. If set, won't restart Nginx using docker  |
| NGINX_LOG_PATH | ./access.log | Yes | Absolute path for file containing Nginx `access.log`. If not set is going to use acces.log |
| BANNED_CONF_FILE | ./banned.conf | No | Absolute path for file containing blocked IPs. If not set, is going to use `banned.conf` as default |
| POLICY | {"404": {"limit": 10, "window": 60,...}} | No | Policy variable, you can also use an file if get hard to mantain |
| POLICY_FILE | ./policy.json | Yes | Absolute path for policy file. |
