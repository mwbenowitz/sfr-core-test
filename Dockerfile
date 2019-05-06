FROM lambci/lambda:build-python3.6
ADD . /code/sfrCore
WORKDIR /code
RUN pip install --upgrade pip
RUN pip install /code/sfrCore -t /code/python