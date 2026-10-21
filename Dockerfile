FROM condaforge/miniforge3:25.3.0-3
LABEL wangx wangx


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SEARCH_PORT=5002

WORKDIR /app

RUN apt-get update -y
RUN apt-get install -y --no-install-recommends tzdata
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo 'Asia/Shanghai' > /etc/timezone
RUN apt-get update && apt-get install -y --no-install-recommends vim-tiny && sed -i '$a\set nocompatible' /etc/vim/vimrc.tiny && sed -i '$a\set backspace=2' /etc/vim/vimrc.tiny

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /home/app --create-home app \
    && mkdir -p /app/workspace /app/output/search_results \
    && chown -R app:app /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .

USER app

CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${SEARCH_PORT:-5002}"]
