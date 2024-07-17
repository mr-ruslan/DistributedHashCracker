#!/bin/bash
echo ************************
echo Starting the replica set
echo ************************

sleep 15 | echo Sleeping

mongosh mongodb://mongodb_0:27017 init-replica.js