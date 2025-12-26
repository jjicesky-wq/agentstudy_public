from tools.base_tool import AIToolBase
from typing import Any
import json
from utilities import logger
import traceback

class AddTool(AIToolBase):
    name: str = "add_tool"

    description: str = "Use this tool to add two numbers"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "left": {
                "type": "number",
                "description": "the left hand side of the add operation"
            },
            "right": {
                "type": "number",
                "description": "the right hand side of the add operation"
            }
        },
        "required": ["left", "right"],
    }

    def _run(self, params: str) -> str:
        """Actual logic of the tool (synchronous)"""
        try:
            param_dict = json.loads(params)
            return str(float(param_dict["left"]) + float(param_dict["right"]))
        except Exception as e:
            logger.error(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.error(f"  {tb}")
            return f"Exception: {e}, try again"