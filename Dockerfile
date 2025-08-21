# 使用 Python 3.11.9 基础镜像
FROM python:3.11.9-slim

# 设置工作目录
WORKDIR /app

# 复制 requirements.txt 并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有项目文件
COPY . .

# 暴露端口（根据代码，默认使用5101和另一个端口）
EXPOSE 5101 5100

# 启动命令
CMD ["python", "start_all.py"]