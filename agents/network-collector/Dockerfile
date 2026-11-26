# On-premises network collector image.
#   docker build -t smecm-collector agents/network-collector
#   docker run -d --name smecm-collector --restart unless-stopped \
#     -p 5514:5514/udp -p 5514:5514/tcp -v smecm-collector:/state \
#     -e SMECM_COLLECTOR_CONFIG=/state/collector.json smecm-collector run
# Enrol once first by running the same image with: enrol --server https://... --token col_...
FROM python:3.13-slim
RUN useradd --create-home --uid 10001 collector && mkdir /state && chown collector /state
COPY smecm_collector.py /opt/smecm/smecm_collector.py
USER collector
ENV SMECM_COLLECTOR_CONFIG=/state/collector.json PYTHONUNBUFFERED=1
EXPOSE 5514/udp 5514/tcp
ENTRYPOINT ["python", "/opt/smecm/smecm_collector.py"]
CMD ["run"]
