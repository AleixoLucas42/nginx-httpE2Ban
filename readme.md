# httpE2Ban for Nginx
This is an simple nginx add-on that block connections based on http status. I know that exists a lot of tools like this but I made for my own to be lightier and also, to be as an "first shield" for applications running behind Nginx. The configuration should be simple and mainly you should be using Nginx on a docker container, but also works for a common Nginx instalation. *Ps: I could do an Nginx with httpE2Ban running inside, but who is going to trust something like this? lol.*

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
(Using docker, nginx access logs is being showed in httpE2Ban container log)

## Setup
For setup you have to do **three steps:**

- Configure an [json policy file](policy.json).
- Nginx configuration
  - Configure your nginx to include the [ban file](banned.conf). Here you can find an example on first line of [nginx.conf](nginx.conf).
  - Configure an condition in your server config to block IPs based on a map in the ban file. Here you can find an example on line 6 to 8 on [nginx.conf](nginx.conf).
- Give access in nginx access logs to httpE2Ban using environment variable.
  - You can run using my [docker image](https://hub.docker.com/repository/docker/aleixolucas/nginx-httpe2ban/) or using Python3

## Running [docker compose](docker-compose.yaml) example (poc)
- Download [repository](https://github.com/AleixoLucas42/nginx-httpE2Ban)
- On repository root, run `docker compose up`
- Access site example on http://localhost:8080
- Access error page example on http://localhost:8080/401
- Access error page more than 5 times and you should be blocked
- Now you can not access no any page on this server.
- Check the [ban file](banned.conf) and your IP should be there next to an epoch timestamp.
- If you wait 2 minutes, the ip should be unbanned due the `BLOCK_TTL` environment variable value.

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
      LOG_LEVEL: "INFO"
      BLOCK_TTL: 7200
    depends_on:
        - nginx
```
1. Mapping the nginx access.log in directory to httpE2Ban have access.
2. Mapping ban file inside Nginx container as read only.
3. This is the timezone of your location, for better time handling.
4. £. This is the way I gave docker cli to httpE2Ban. You have to do the same if you have no other way to access your Nginx, to avoid this, you can use the environment variable `RELOAD_NGINX_CUSTOM_CMD` so httpE2Ban can use this command to access the nginx and send nginx reload. Check if your docker socked and binary are in the same path as docker compose if you have any trouble.

## Run without docker
To run withou docker, you should have pip3 and python3.9 installed.
- Create virtual environment
> python3 -m venv .venv
- Activate venv
> source .venv/bin/activate # Linux

> C:\ .venv\Scripts\activate.bat # Window
- Install packages on virtual environment
> pip3 install -r requirements.txt
- Create the banned file
```sh
# Should be exacly like this when first create
cat <<EOF > $HOME/nginx-httpE2Ban/banned.conf
map \$remote_addr \$blocked {
    default 0;
}
EOF
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
| NGINX_CONTAINER_NAME | nginx-prod | No | Nginx container name. If not set, httpE2Ban will restart the first container that is running Nginx image. |
| RELOAD_NGINX_CUSTOM_CMD | ssh user@123.456.789.0 "nginx -s reload" | No | Custom command to restart Nginx. If set, won't restart Nginx using docker.  |
| NGINX_LOG_PATH | ./access.log | Yes | Absolute path for file containing Nginx `access.log`. If not set is going to use `acces.log` as default. |
| BANNED_CONF_FILE | ./banned.conf | No | Absolute path for file containing blocked IPs. If not set, is going to use `banned.conf` as default. |
| POLICY | {"404": {"limit": 10, "window": 60,...}} | No | Policy variable, you can also use an file if get hard to mantain. |
| POLICY_FILE | ./policy.json | Yes | Absolute path for policy file. |
| STARTUP_DELAY | 10 | No | In seconds, how long to wait until start httpE2Ban. Default value is 5. |
| LOG_LEVEL | DEBUG | No | Possibilities: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Default is `INFO`.|
| NGINX_LOG_JSON_MAP | {"ip_address":"remote_addr"...} | No | If your log format is not in default and you are using json as log, this is an workaround to use httpE2Ban. |
| BLOCK_TTL_CHECK_DELAY | 60 | No | In seconds, how long to wait to unban an IP. Default is `60`. |
| BLOCK_TTL | 7200 | No | The time the IP will be blocked. If not configured, the `block is permanent`. |


## How to map log format when using json
If your log format is not the default format that Nginx provide and you are using a json format, you can still use httpE2Ban, you just need to map some information that httpE2Ban needs. Your log should not contain nothing besides json and should start and finish with brackets. **If you are not using one of these formats (default/json) the only way to make it work is change the source code and rebuild the httpE2Ban.**

#### Map example
The map is done using NGINX_LOG_JSON_MAP environment variable, in a key value json format, you can find an example in a commented line on [docker compose](docker-compose.yaml) file.
httpE2Ban needs these information:
|    Name      |                           Description                              |
|------------  | -----------------------------------------------------------------  | 
| ip_address   | The client remote address. (This is the ip that should be blocked) |
| datetime     | Request time, generally on log                                     |
| request      | The request received                                               |
| url          | Url requested                                                      |
| http_version | Wich http version being used, like "HTTP/1.1"                      |
| status_code  | The request status code present in log                             |
| user_agent   | The user agend that client used to reach Nginx                     |

If the Nginx log line is like:
```json
{"msec":"1724864433.591","connection":"1","connection_requests":"1","pid":"42","request_id":"bf76bf04c6a423ed20bd2cfb49c5913a","request_length":"837","remote_addr":"172.18.0.1","remote_user":"-","remote_port":"49094","time_local":"28/Aug/2024:14:00:33 -0300","time_iso8601":"2024-08-28T14:00:33-03:00","request":"GET / HTTP/1.1","request_uri":"/","args":"-","status":"304","body_bytes_sent":"0","bytes_sent":"179","http_referer":"-","http_user_agent":"Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0","http_x_forwarded_for":"-","http_host":"localhost:8080","server_name":"site-example.com","request_time":"0.000","upstream":"-","upstream_connect_time":"-","upstream_header_time":"-","upstream_response_time":"-","upstream_response_length":"-","upstream_cache_status":"-","ssl_protocol":"-","ssl_cipher":"-","scheme":"http","request_method":"GET","server_protocol":"HTTP/1.1","pipe":".","gzip_ratio":"-","http_cf_ray":"-"}
```
So the NGINX_LOG_JSON_MAP variable should be:
```bash
NGINX_LOG_JSON_MAP={"ip_address":"remote_addr","datetime":"time_local","request":"request","url":"http_referer","http_version":"server_protocol","status_code":"status","user_agent":"http_user_agent"}
```


# FAQ
### Does this work when not using container to run Nginx 
- Yes, you can run Python or use the binary file on [releases](https://github.com/AleixoLucas42/nginx-httpE2Ban/releases)
### Where is the Nginx container logs?
- The requests logs are redirected to httpE2Ban container, the same log that should out in Nginx container, now is on httpE2Ban container. Why? Because I can't make work in both yet.
### Can I use if my Nginx log format is different from default?
- You can just use if your log format is default or in json format, without anything else. Just read the 'how to map json' section and you'll be fine.
### Why not use fail2ban or another similar know tool?
- You can use, maybe you should use, the point of httpE2Ban is the easy way to make work, i'm not doing to replace any tool, just developing to learn.
### I ran the docker compose and its not accessing the service
- Try to change the port on docker compose file and check if any file was altered after clone the repository.
### Can the logs be more or less detailed?
- Yes you can use the environment variable LOG_LEVEL to change logs, in production I recomend to use value `ERROR` or `CRITICAL`.
### What is the meaning of httpE2Ban?
- It's just "ban when get some http Error that came from request status code".

## 
- [Github](https://github.com/AleixoLucas42/nginx-httpE2Ban)
- [Dockerhub](https://hub.docker.com/repository/docker/aleixolucas/nginx-httpe2ban/)