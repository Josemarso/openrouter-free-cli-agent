import argparse
import base64
import mimetypes
import os
import sys
import json
import subprocess
import openai
from pathlib import Path

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
# Free AI model selected by OpenRouter via its "openrouter/free" solution.
MODEL= "openrouter/free"


## TOOL ADVERTISING
read_tool = {
    "type":"function",
    "function":{
        "name":"read_file_content",
        "description":"Read and return the content of a file",
        "parameters":{
            "type":"object",
            "properties":{
                "file_path":{
                    "type":"string",
                    "description":"The path to the file to read"
                }
            }
        },
        "required":["file_path"]
    }
}

write_tool = {
    "type":"function",
    "function":{
        "name":"write_file_content",
        "description":"Write content to a file",
        "parameters":{
            "type":"object",
            "required":["file_path", "content"],
            "properties":{
                "file_path":{
                    "type": "string",
                    "description": "The path of the file to write to"
                },
                "content":{
                    "type":"string",
                    "description": "The content to be written to the file"
                }
            }
        }
    }
}

bash_tool = {
    "type":"function",
    "function":{
        "name":"execute_bash_command",
        "description":"Execute a shell command",
        "parameters":{
            "type":"object",
            "required":["command"],
            "properties":{
                "command":{
                    "type":"string",
                    "description": "The command to execute"
                }
            }
        }
    }
}

image_send_tool = {
    "type":"function",
    "function":{
        "name":"send_image",
        "description":"Reads an image, encodes it to base64 and sends back the utf-8 string representation of said image to the model.",
        "parameters":{
            "type":"object",
            "required":["file_path"],
            "properties":{
                "file_path":{
                    "type":"string",
                    "description": "The path to the image file to read and send to the model"
                }
            }
        }
    }
}


## TOOL IMPLEMENTATION
def read_file(json_parameters, tool_call_id):
    try:
        file_path = json.loads(json_parameters)["file_path"]
        file_content = Path(file_path).read_text()
        tool_message = [ {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": file_content
        } ]
        return tool_message
    
    except FileNotFoundError:
        return f"ERROR: file not found — {file_path}"
    except Exception as e:
        return f"ERROR: unexpected error: {e}"

def write_file(json_parameters, tool_call_id):
    try:
        file_path = json.loads(json_parameters)["file_path"]
        content = json.loads(json_parameters)["content"]
        with open(file_path, "w") as file:
            file.write(content)
        file_content = Path(file_path).read_text()
        tool_message = [ {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": file_content
        } ]
        return tool_message
    
    except FileNotFoundError:
        return f"ERROR: file not found — {file_path}"
    except Exception as e:
        return f"ERROR: unexpected error: {e}"

def bash_command(json_parameters, tool_call_id):
    command = json.loads(json_parameters)["command"]
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    command_message = result.stderr if result.stderr else result.stdout
    tool_message = [ {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": command_message
    } ]
    return tool_message

def image_send(json_parameters, tool_call_id):
    try:
        file_path = json.loads(json_parameters)["file_path"]
        # Guess the MIME type of the image or assign default
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "image/jpeg"

        # Response is built of an explanatory text and the image (encoded in base64 and passed as utf-8)
        content_return = [ {"type": "text", "text": "For the image within this message, apply the instructions from the first message sent by the user in this chat"} ]
        with open(file_path, "rb") as file:
            readable_base64_data = base64.b64encode(file.read()).decode('utf-8')
            content_return.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{readable_base64_data}"
                }
            })

        # Returns a tool confirmation message to the model and another user-role message with the encoded image as input.
        # This 2 message approach seems to make it easier for "openrouter/free" to re-select a model that accepts images as input
        # reducing the chances of an invalid input format error. This approach can be bypassed if an specific model with image input
        # is selected from the start, instead of "openrouter/free"
        tool_result = [ 
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": "Image encoded correctly, its content will be available in image_url format in the next message with 'role': 'user'"
            }, 
            {
                "role": "user",
                "content": content_return
            } ]
        return tool_result
    
    except FileNotFoundError:
        return f"ERROR: file not found — {file_path}"
    except Exception as e:
        return f"ERROR: unexpected error: {e}"


## TOOL HANDLER
function_handler = {
    "read_file_content" : read_file,
    "write_file_content" : write_file,
    "execute_bash_command" : bash_command,
    "send_image" : image_send
}


## SENDS THE PROMPT to the model alongside the conversation context/history and the advertised tools. Returns the model response
def send_prompt(client,chat):
    ai_reply = client.chat.completions.create(
        model=MODEL,
        extra_body={
            "provider": {
                "require_parameters": True
            }
        },
        messages=chat,
        tools=[
            read_tool,
            write_tool,
            bash_tool,
            image_send_tool
        ]
    )
    # Prints the model used by "openrouter/free" to handle the prompt
    print(f"------------------------------------------------\nUSING MODEL: {ai_reply.model}\n------------------------------------------------",
            file=sys.stderr)
    return ai_reply


## MAIN LOOP
def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = openai.OpenAI(api_key=API_KEY, base_url=BASE_URL)

    messages = [{"role": "user", "content": args.p}]
    while True:
        chat = send_prompt(client, messages)
        if not chat.choices or len(chat.choices) == 0:
            raise RuntimeError("No choices available in the model response")
    
        if not chat.choices[0].message.tool_calls or len(chat.choices[0].message.tool_calls) == 0:
            print(chat.choices[0].message.content)
            break
        
        messages.append(chat.choices[0].message)
        # Checks if the model requested tool usage and, if so, returns the tool result
        for tool_call in chat.choices[0].message.tool_calls:
            if tool_call.type == "function":
                    tool_result = function_handler[tool_call.function.name](tool_call.function.arguments, tool_call.id)
                    messages.extend(tool_result)


if __name__ == "__main__":
    main()
