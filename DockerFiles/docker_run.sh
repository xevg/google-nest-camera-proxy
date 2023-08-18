#!/bin/bash

echo "$NEST_TOKEN" > /root/.config/nest/token_cache
cat > /root/.config/nest/config <<EOF
[NEST]
    client_id = $CLIENT_ID
    client_secret = $CLIENT_SECRET
    project_id = $PROJECT_ID

[AUTH]
    client_id = $CLIENT_ID
    client_secret = $CLIENT_SECRET
    project_id = $PROJECT_ID
    access_token_cache_file = /root/.config/nest/token_cache

[RTSP_SERVER]
    executable = /code/mediamtx
    config_filename = /root/.config/nest/mediamtx.yml
EOF

sed -i "s/<<<readUser>>>/$MTX_READUSER/g" /root/.config/nest/mediamtx.yml
sed -i "s/<<<readPass>>>/$MTX_READPASS/g" /root/.config/nest/mediamtx.yml

google-nest-camera-proxy

