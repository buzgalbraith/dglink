FROM ubuntu:20.04

# Needed to forego timezone configuration
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /sw
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y \
    && apt-get upgrade -y \
    && apt-get -y install build-essential \
    && apt-get install -y git wget curl nano zip unzip bzip2 gcc graphviz \
        graphviz-dev pkg-config python3-pip cmake libxml2-dev swig \
        software-properties-common dirmngr apt-transport-https \
        gnupg gnupg2 ca-certificates lsb-release ubuntu-keyring

# Install neo4j
RUN curl -fsSL https://debian.neo4j.com/neotechnology.gpg.key | \
        gpg --dearmor -o /usr/share/keyrings/neo4j.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/neo4j.gpg] https://debian.neo4j.com stable latest" | \
        tee -a /etc/apt/sources.list.d/neo4j.list \
    && ln -s /usr/bin/python3 /usr/bin/python \
    && apt-get update -y \
    && apt-get install -y neo4j=1:2025.10.1

# Install neo4j apoc core (bundled with neo4j) - simply move the core jar to the plugins directory
RUN mv /var/lib/neo4j/labs/apoc-2025.10.1-core.jar /var/lib/neo4j/plugins/


## apoc extended installation - see https://neo4j.com/labs/apoc/2025/installation/
# Retrieve jar file for apoc extended
RUN wget https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases/download/2025.10.0/apoc-2025.10.0-extended.jar -O /var/lib/neo4j/plugins/apoc-2025.10.0-extended.jar

# Set custom configuration to enable apoc extended and allow connections
# (core) https://neo4j.com/labs/apoc/2025/installation/#restricted
# (extended) https://neo4j.com/labs/apoc/2025/installation/#restricted

# dbms.security.procedures.allowlist is set to '*' by default so we don't touch that
# line in the config - this allows all procedures that _don't_ use the internal API

# For procedures that use the internal API we need to explicitly allow them
RUN echo "dbms.security.procedures.unrestricted=apoc.*" >> /etc/neo4j/neo4j.conf
# Disabling neo4j authentication.
RUN sed -i 's/#dbms.security.auth_enabled/dbms.security.auth_enabled/' /etc/neo4j/neo4j.conf
# Enables writing local files to disk
# https://neo4j.com/docs/apoc/current/config/#_apoc_export_file_enabled
# NOTE: apoc settings must be in their own conf file, apoc.conf, in the same
# directory as neo4j.conf
RUN echo "apoc.export.file.enabled=true" >> /etc/neo4j/apoc.conf

# Set up external traffic and basic auth
RUN sed -i 's/#server.default_listen_address/server.default_listen_address/' /etc/neo4j/neo4j.conf

# Ingest graph content into neo4j
# COPY kg /sw/kg
COPY graph /sw/


RUN neo4j-admin database import full \
    --delimiter='TAB' \
    --verbose \
    --skip-duplicate-nodes=true \
    --skip-bad-relationships=true \
    --relationships /sw/edges.tsv \
    --nodes /sw/nodes.tsv \
      || (echo "=== IMPORT FAILED, SHOWING /sw/import.report ===" && cat /sw/import.report && exit 1)


ENV DOCKERIZED="TRUE"
ENV NEO4J_URL="bolt://localhost:7687"

COPY startup.sh  /sw/startup.sh

ENTRYPOINT ["/bin/bash",  "/sw/startup.sh"]

#
# # Retrieves jar file needed to install apoc
# RUN wget https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases/download/4.4.0.30/apoc-4.4.0.30-all.jar -O /var/lib/neo4j/plugins/apoc-4.4.0.30-all.jar
# #
# # # Set custom configuration to enable apoc
# RUN echo "dbms.security.procedures.unrestricted=apoc.*" >> /etc/neo4j/neo4j.conf
# RUN echo "apoc.export.file.enabled=true" >> /etc/neo4j/neo4j.conf
# #
# COPY graph /sw/
# # # Ingest graph content into neo4j
# RUN sed -i 's/#dbms.default_listen_address/dbms.default_listen_address/' /etc/neo4j/neo4j.conf
# RUN sed -i 's/#dbms.security.auth_enabled/dbms.security.auth_enabled/' /etc/neo4j/neo4j.conf
# RUN neo4j-admin database import --delimiter='TAB' --skip-duplicate-nodes=true --skip-bad-relationships=true \
#     --relationships /sw/edges.tsv \
#     --nodes /sw/nodes.tsv
#
# ENV DOCKERIZED="TRUE"
# ENV NEO4J_URL="bolt://localhost:7687"
#
# ENTRYPOINT ["/bin/bash", "/sw/startup.sh"]
# COPY startup.sh /sw/startup.sh
