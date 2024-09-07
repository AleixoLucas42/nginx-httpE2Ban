FROM ubuntu:24.10

WORKDIR /httpe2ban
ARG SSH_PATH=/root/.ssh/ssh-file

RUN apt update \
    && apt install -y python3 python3-pip ssh curl wget

RUN install -D /dev/null ${SSH_PATH}
RUN chmod 600 ${SSH_PATH}

RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY main.py .
COPY requirements.txt .

RUN pip3 install -r requirements.txt --break-system-packages

ENTRYPOINT [ "python3" ]
CMD [ "-u", "main.py" ]