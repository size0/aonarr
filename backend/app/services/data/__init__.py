"""数据采集与预测服务"""
from app.services.data.collector import DataCollector
from app.services.data.predictor import ReadPredictor

__all__ = ["DataCollector", "ReadPredictor"]
