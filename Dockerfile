FROM python:3.11-alpine

WORKDIR /app

# 拷贝核心脚本
COPY app.py .

# 设定默认环境变量
ENV SUB_TOKEN=my_secure_token
ENV UPDATE_INTERVAL=86400

# 暴露服务端口
EXPOSE 50000

# -u 开启 Python 无缓存输出，使 docker logs 可以实时查看打印
CMD ["python", "-u", "app.py"]
