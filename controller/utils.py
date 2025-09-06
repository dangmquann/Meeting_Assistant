import yaml
from fastapi import HTTPException
from typing import Any, List, Literal, Optional



def normalize_http_exception(exc = None, status_code=500, type_error: Literal["dialog", "notification", "normal"] = "dialog", message: str = "An unexpected error occurred"):
    if isinstance(exc, HTTPException):
        exc.detail["type_error"] = type_error
        return exc
    elif isinstance(exc, Exception):
        return HTTPException(status_code=status_code, detail={
            "error_code": 500,
            "type_error": type_error,
            "message": str(exc)
        })
    else:
        return HTTPException(status_code=status_code, detail={
            "error_code": 500,
            "type_error": type_error,
            "message": message
        })
    
def load_cfg(cfg_file):
    """
    Load configuration from a YAML config file
    """
    cfg = None
    with open(cfg_file, "r") as f:
        try:
            cfg = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(exc)

    return cfg