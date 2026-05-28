FROM apache/dolphinscheduler-standalone-server:3.2.2

USER root

# 切换阿里云镜像源（加速国内构建）
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list \
 && sed -i 's|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list

# 安装 Python3（DataX 运行依赖）和 MySQL 客户端（SQL SHELL 任务依赖）
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends python3 default-mysql-client \
 && ln -sf /usr/bin/python3 /usr/bin/python \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# 确保 java 和 python 在所有 shell 环境下可用
# DS worker 以 sudo -u root -i 执行 shell 任务，需要 /etc/profile.d 生效
RUN ln -sf /opt/java/openjdk/bin/java /usr/bin/java \
 && echo 'export JAVA_HOME=/opt/java/openjdk' > /etc/profile.d/java.sh \
 && echo 'export PATH=$JAVA_HOME/bin:$PATH' >> /etc/profile.d/java.sh \
 && echo 'export DATAX_HOME=/opt/datax' > /etc/profile.d/datax.sh

ENV JAVA_HOME=/opt/java/openjdk
ENV DATAX_HOME=/opt/datax

# 降低 JVM heap：默认 -Xms4g -Xmx4g 在 mem_limit:4g 容器内会耗尽 OS 内存导致卡死
# 2g heap + 2g OS/metaspace 留量，实测稳定
RUN printf -- '-Xms1g\n-Xmx2g\n-Xmn512m\n\n-XX:+IgnoreUnrecognizedVMOptions\n-XX:+PrintGCDateStamps\n-XX:+PrintGCDetails\n-Xloggc:gc.log\n\n-XX:+ExitOnOutOfMemoryError\n-XX:+HeapDumpOnOutOfMemoryError\n-XX:HeapDumpPath=dump.hprof\n\n-Duser.timezone=${SPRING_JACKSON_TIME_ZONE}\n' \
    > /opt/dolphinscheduler/bin/jvm_args_env.sh
