FROM python:3.11
LABEL authors="xev"

# ENV NEST_TOKEN=${NEST_TOKEN} \
# python:
ENV  PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PYTHONDONTWRITEBYTECODE=1 \
  # pip:
  PIP_NO_CACHE_DIR=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PIP_DEFAULT_TIMEOUT=100 \
  PIP_ROOT_USER_ACTION=ignore

# System deps:
# RUN pip install google-nest-camera-proxy

COPY DockerFiles/docker_run.sh /code/
COPY DockerFiles/mediamtx /code/
COPY DockerFiles/google-nest-camera-proxy.ini /root/.config/nest/config
COPY DockerFiles/mediamtx.yml /root/.config/nest/
COPY . /project/

RUN pip install /project

# ENTRYPOINT ["top", "-b"]
ENTRYPOINT ["/bin/bash", "/code/docker_run.sh"]


