import os
import smtplib
import ssl
import logging
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import yaml

import sponsor_filter
from searchers import search_all_streaming

logger = logging.getLogger(__name__)


def load_config(path: str = "digest_config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)
