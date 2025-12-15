"""
Prometheus Remote Write v2 Protocol Implementation
Sends metrics to OpenTelemetry Collector's prometheusremotewrite receiver
"""
import time
import snappy
import requests
import struct
from typing import List, Dict, Any


def encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint"""
    result = bytearray()
    while value > 0x7f:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value & 0x7f)
    return bytes(result)


def encode_string(field_num: int, value: str) -> bytes:
    """Encode a string field"""
    encoded_value = value.encode('utf-8')
    return (encode_varint((field_num << 3) | 2) +  # Wire type 2 (length-delimited)
            encode_varint(len(encoded_value)) +
            encoded_value)


def encode_double(field_num: int, value: float) -> bytes:
    """Encode a double field"""
    return (encode_varint((field_num << 3) | 1) +  # Wire type 1 (64-bit)
            struct.pack('<d', value))


def encode_int64(field_num: int, value: int) -> bytes:
    """Encode an int64 field"""
    return encode_varint((field_num << 3) | 0) + encode_varint(value)  # Wire type 0 (varint)


def encode_label(name: str, value: str) -> bytes:
    """
    Encode a Label message:
    message Label {
      string name = 1;
      string value = 2;
    }
    """
    result = bytearray()
    result.extend(encode_string(1, name))
    result.extend(encode_string(2, value))
    return bytes(result)


def encode_sample(value: float, timestamp: int) -> bytes:
    """
    Encode a Sample message:
    message Sample {
      double value = 1;
      int64 timestamp = 2;  # milliseconds since epoch
    }
    """
    result = bytearray()
    result.extend(encode_double(1, value))
    result.extend(encode_int64(2, timestamp))
    return bytes(result)


def encode_timeseries(labels: Dict[str, str], samples: List[Dict[str, Any]]) -> bytes:
    """
    Encode a TimeSeries message:
    message TimeSeries {
      repeated Label labels = 1;
      repeated Sample samples = 2;
    }
    """
    result = bytearray()
    
    # Encode labels
    for name, value in labels.items():
        label_bytes = encode_label(name, value)
        result.extend(encode_varint((1 << 3) | 2))  # Field 1, wire type 2
        result.extend(encode_varint(len(label_bytes)))
        result.extend(label_bytes)
    
    # Encode samples
    for sample in samples:
        sample_bytes = encode_sample(sample['value'], sample['timestamp'])
        result.extend(encode_varint((2 << 3) | 2))  # Field 2, wire type 2
        result.extend(encode_varint(len(sample_bytes)))
        result.extend(sample_bytes)
    
    return bytes(result)


def encode_write_request(timeseries_list: List[Dict[str, Any]]) -> bytes:
    """
    Encode a WriteRequest message for Remote Write v2:
    message WriteRequest {
      repeated TimeSeries timeseries = 1;
    }
    """
    result = bytearray()
    
    for ts_data in timeseries_list:
        ts_bytes = encode_timeseries(ts_data['labels'], ts_data['samples'])
        result.extend(encode_varint((1 << 3) | 2))  # Field 1, wire type 2
        result.extend(encode_varint(len(ts_bytes)))
        result.extend(ts_bytes)
    
    return bytes(result)


class PrometheusRemoteWriteV2Client:
    """Client for sending metrics via Prometheus Remote Write v2 protocol"""
    
    def __init__(self, url: str):
        self.url = url
        self.session = requests.Session()
    
    def send(self, timeseries: List[Dict[str, Any]]) -> requests.Response:
        """
        Send time series data via Remote Write v2
        
        Args:
            timeseries: List of dicts with 'labels' and 'samples' keys
                       labels: Dict[str, str] - metric labels including '__name__'
                       samples: List[Dict] - each with 'value' (float) and 'timestamp' (int, milliseconds)
        
        Returns:
            Response object from the HTTP POST
        """
        # Encode the protobuf message
        proto_data = encode_write_request(timeseries)
        
        # Compress with snappy
        compressed_data = snappy.compress(proto_data)
        
        # Set headers for Remote Write v2
        headers = {
            'Content-Encoding': 'snappy',
            'Content-Type': 'application/x-protobuf; proto=io.prometheus.write.v2.Request',
            'User-Agent': 'tinyolly-demo/1.0',
            'X-Prometheus-Remote-Write-Version': '2.0.0',
        }
        
        # Send the request
        response = self.session.post(self.url, headers=headers, data=compressed_data)
        response.raise_for_status()
        return response
