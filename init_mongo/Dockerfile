FROM mongo:5

WORKDIR /usr/scr/configs

COPY init-replica.js .
COPY setup.sh .

CMD [ "./setup.sh"]