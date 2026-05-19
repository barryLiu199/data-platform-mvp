FROM apache/dolphinscheduler-standalone-server:3.2.2

USER root

# 切换阿里云镜像源（加速国内构建）
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list \
 && sed -i 's|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list

# 安装 Python3（DataX 运行依赖）
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends python3 \
 && ln -sf /usr/bin/python3 /usr/bin/python \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
