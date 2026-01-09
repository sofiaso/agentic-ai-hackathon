"""AWS Bedrock client wrapper for LLM calls."""

import json
import logging
import os
import time
from typing import Any, TypeVar

import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError

# Set up logger for LLM calls
logger = logging.getLogger(__name__)

from iac_agent.llm.prompts import load_prompt
from iac_agent.llm.schemas import (
    FedRampMapperOutput,
    RemediationAdvisorOutput,
    RouterOutput,
    ToolRouterOutput,
)
from iac_agent.llm.tool_catalog import get_fallback_tool, get_tool_catalog

T = TypeVar("T")


class LLMCallResult:
    """Result from an LLM call with metadata."""

    def __init__(
        self,
        text: str,
        latency_seconds: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ):
        self.text = text
        self.latency_seconds = latency_seconds
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class BedrockClient:
    """AWS Bedrock client for LLM inference."""

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
    ):
        """
        Initialize Bedrock client.

        Args:
            model_id: Bedrock model ID (defaults to env BEDROCK_MODEL_ID or "eu.amazon.nova-2-lite-v1:0")
            region: AWS region (defaults to env AWS_REGION/AWS_DEFAULT_REGION or "eu-north-1")
        """
        # Get defaults from environment or use hardcoded defaults
        env_model_id = os.getenv("BEDROCK_MODEL_ID")
        self.model_id = model_id or env_model_id or "eu.amazon.nova-2-lite-v1:0"
        # Store env_model_id for potential fallback
        self._env_model_id = env_model_id
        
        # Log which source was used
        if model_id:
            logger.info(f"BedrockClient: Using model_id from parameter: {model_id}")
        elif env_model_id:
            logger.info(f"BedrockClient: Using BEDROCK_MODEL_ID from environment: {env_model_id}")
        else:
            logger.info(f"BedrockClient: Using default model_id: eu.amazon.nova-2-lite-v1:0")
        self.region = (
            region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "eu-north-1"
        )
        self.client: Any | None = None
        self.use_bearer_token = False
        self.bearer_token: str | None = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize boto3 Bedrock runtime client."""
        try:
            # Check for Bearer Token authentication first
            bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
            
            if bearer_token:
                # Use Bearer Token authentication
                logger.debug("Using Bearer Token authentication for Bedrock")
                # Store bearer token for use in API calls
                self.bearer_token = bearer_token
                # Create client without credentials (will use Bearer Token in requests)
                self.client = boto3.client("bedrock-runtime", region_name=self.region)
                self.use_bearer_token = True
            else:
                # Use standard AWS credentials
                logger.debug("Using standard AWS credentials for Bedrock")
                self.client = boto3.client("bedrock-runtime", region_name=self.region)
                self.use_bearer_token = False
                self.bearer_token = None
            
            logger.debug(f"Bedrock client initialized: region={self.region}, model={self.model_id}, auth={'Bearer Token' if self.use_bearer_token else 'AWS Credentials'}")
        except Exception as e:
            # If initialization fails, client remains None
            # Calls will fail gracefully
            logger.error(f"Failed to initialize Bedrock client: {type(e).__name__}: {str(e)}")
            self.client = None
            self.use_bearer_token = False
            self.bearer_token = None

    def call_llm_text(
        self, system_prompt: str | None = None, user_prompt: str = ""
    ) -> LLMCallResult | None:
        """
        Call LLM with system and user prompts, returning raw text and metadata.

        Args:
            system_prompt: Optional system prompt
            user_prompt: User prompt content

        Returns:
            LLMCallResult with text, latency, and token usage, or None if failed
        """
        if not self.client:
            logger.warning("LLM client not initialized, skipping call")
            return None

        logger.info(f"Calling LLM: model={self.model_id}, region={self.region}")
        start_time = time.time()

        try:
            # Prefer Converse API for Nova models (and other modern models)
            # Check if model supports Converse API by checking model ID pattern
            # Nova models can have regional prefixes: eu.amazon.nova-, us.amazon.nova-, amazon.nova-
            use_converse = (
                ".amazon.nova-" in self.model_id
                or self.model_id.startswith("amazon.nova-")
                or self.model_id.startswith("anthropic.claude-3")
            )

            api_type = "Converse API" if use_converse else "invoke_model API"
            logger.debug(f"Using {api_type} for model {self.model_id}")

            if use_converse:
                response = self._call_converse_api(system_prompt, user_prompt)
            else:
                # Fallback to invoke_model for older models
                response = self._call_invoke_model(system_prompt, user_prompt)

            if not response:
                logger.warning("LLM call returned no response")
                return None

            latency = time.time() - start_time

            # Extract text and metadata from response
            text = response.get("text", "")
            usage = response.get("usage", {})
            input_tokens = usage.get("inputTokens")
            output_tokens = usage.get("outputTokens")

            # Log response summary
            text_preview = text[:200] + "..." if len(text) > 200 else text
            logger.info(
                f"LLM response received: latency={latency:.2f}s, "
                f"input_tokens={input_tokens or 'N/A'}, output_tokens={output_tokens or 'N/A'}, "
                f"response_length={len(text)} chars"
            )
            logger.debug(f"LLM response preview: {text_preview}")
            
            # Print full response to console
            print("\n" + "="*80)
            print("LLM RESPONSE:")
            print("="*80)
            print(text)
            print("="*80 + "\n")

            return LLMCallResult(
                text=text,
                latency_seconds=latency,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except (ClientError, BotoCoreError, KeyError, json.JSONDecodeError, Exception) as e:
            logger.error(f"LLM call failed: {type(e).__name__}: {str(e)}")
            return None

    def _call_converse_api(
        self, system_prompt: str | None, user_prompt: str
    ) -> dict[str, Any] | None:
        """Call Bedrock Converse API (preferred for Nova and Claude 3)."""
        try:
            # Build messages list
            messages = [{"role": "user", "content": [{"text": user_prompt}]}]

            # Build request parameters
            request_params: dict[str, Any] = {
                "modelId": self.model_id,
                "messages": messages,
                "inferenceConfig": {
                    "maxTokens": 4096,
                    "temperature": 0.0,  # Deterministic for JSON output
                },
            }

            # Add system prompt if provided (must be a list of content blocks)
            if system_prompt:
                request_params["system"] = [{"text": system_prompt}]

            logger.debug(f"Calling Converse API with model {self.model_id}")
            
            # If using Bearer Token, use direct HTTP request
            if self.use_bearer_token and self.bearer_token:
                response_data = self._call_converse_api_with_bearer_token(request_params)
                if not response_data:
                    return None
                # Convert to same format as boto3 response
                return response_data
            
            response = self.client.converse(**request_params)

            # Extract response
            output = response.get("output", {})
            message = output.get("message", {})
            content = message.get("content", [])

            # Extract text from content
            text = ""
            for item in content:
                if item.get("text"):
                    text += item["text"]

            # Extract usage metadata
            usage = response.get("usage", {})

            if not text:
                logger.warning("Converse API returned empty text response")
                return None

            return {"text": text, "usage": usage}

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"Converse API ClientError: {error_code} - {error_message}")
            # If Converse API fails, fallback to invoke_model
            logger.info("Falling back to invoke_model API")
            return self._call_invoke_model(system_prompt, user_prompt)
        except Exception as e:
            logger.error(f"Converse API error: {type(e).__name__}: {str(e)}")
            # If Converse API fails, fallback to invoke_model
            logger.info("Falling back to invoke_model API")
            return self._call_invoke_model(system_prompt, user_prompt)

    def _call_converse_api_with_bearer_token(
        self, request_params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Call Bedrock Converse API using Bearer Token authentication."""
        try:
            # Build the API endpoint URL
            # For Bearer Token API, use the model_id as-is (should be inference profile if needed)
            logger.debug(f"Bearer Token Converse API: model_id={self.model_id}, region={self.region}")
            endpoint_url = f"https://bedrock-runtime.{self.region}.amazonaws.com/model/{self.model_id}/converse"
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.bearer_token}",
            }
            
            # Make the HTTP request
            response = requests.post(
                endpoint_url,
                json=request_params,
                headers=headers,
                timeout=60,
            )
            
            # Check for errors
            response.raise_for_status()
            
            # Parse response
            response_data = response.json()
            
            # Extract response in the same format as boto3 response
            output = response_data.get("output", {})
            message = output.get("message", {})
            content = message.get("content", [])
            
            # Extract text from content
            text = ""
            for item in content:
                if item.get("text"):
                    text += item["text"]
            
            # Extract usage metadata
            usage = response_data.get("usage", {})
            
            return {"text": text, "usage": usage}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Bearer Token API request failed: {type(e).__name__}: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error response: {error_detail}")
                    
                    # Check if error is about unsupported model with on-demand throughput
                    error_message = error_detail.get("message", "")
                    if "on-demand throughput isn't supported" in error_message or "inference profile" in error_message.lower():
                        logger.warning(
                            f"Model {self.model_id} is not supported with Bearer Token API. "
                            f"Bearer Token API requires an inference profile ID, not a direct model ID. "
                            f"Consider using a model from .env.local (BEDROCK_MODEL_ID) or an inference profile ID."
                        )
                        # If we have a different model in .env.local and current model was from CLI, suggest using it
                        if self._env_model_id and self._env_model_id != self.model_id:
                            logger.info(
                                f"Note: BEDROCK_MODEL_ID in .env.local is '{self._env_model_id}', "
                                f"which might work better with Bearer Token API. "
                                f"Try removing --model-id to use the .env.local model."
                            )
                except:
                    logger.error(f"Error response text: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Bearer Token API error: {type(e).__name__}: {str(e)}")
            return None

    def _call_invoke_model(
        self, system_prompt: str | None, user_prompt: str
    ) -> dict[str, Any] | None:
        """Call Bedrock invoke_model API (fallback for older models or if Converse fails)."""
        try:
            logger.debug(f"Calling invoke_model API with model {self.model_id}")
            # Determine body format based on model
            # Nova models can have regional prefixes: eu.amazon.nova-, us.amazon.nova-, amazon.nova-
            if ".amazon.nova-" in self.model_id or self.model_id.startswith("amazon.nova-"):
                # Nova Micro format (if not using Converse)
                body = json.dumps(
                    {
                        "inputText": user_prompt,
                        "inferenceConfig": {
                            "maxTokens": 4096,
                            "temperature": 0.0,
                            "topP": 0.9,
                        },
                    }
                )
            elif self.model_id.startswith("anthropic.claude-"):
                # Claude format
                messages = [{"role": "user", "content": user_prompt}]
                body = json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 4096,
                        "messages": messages,
                        "system": system_prompt if system_prompt else None,
                    }
                )
            else:
                # Generic format
                body = json.dumps({"prompt": user_prompt, "max_tokens": 4096})

            # If using Bearer Token, use direct HTTP request
            if self.use_bearer_token and self.bearer_token:
                response_body = self._call_invoke_model_with_bearer_token(body)
                if not response_body:
                    return None
            else:
                response = self.client.invoke_model(modelId=self.model_id, body=body)
                response_body = json.loads(response["body"].read())

            # Extract text based on model response format
            text = ""
            usage = {}

            if "outputText" in response_body:
                # Nova format
                text = response_body["outputText"]
            elif "content" in response_body:
                # Claude format
                content = response_body.get("content", [])
                if content and isinstance(content, list):
                    text = content[0].get("text", "")
                usage = {
                    "inputTokens": response_body.get("usage", {}).get("input_tokens"),
                    "outputTokens": response_body.get("usage", {}).get("output_tokens"),
                }
            else:
                # Generic
                text = str(response_body)

            if not text:
                logger.warning("invoke_model API returned empty text response")
                return None

            return {"text": text, "usage": usage}

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"invoke_model API ClientError: {error_code} - {error_message}")
            return None
        except Exception as e:
            logger.error(f"invoke_model API error: {type(e).__name__}: {str(e)}")
            return None

    def _call_invoke_model_with_bearer_token(self, body: str) -> dict[str, Any] | None:
        """Call Bedrock invoke_model API using Bearer Token authentication."""
        try:
            # Build the API endpoint URL
            endpoint_url = f"https://bedrock-runtime.{self.region}.amazonaws.com/model/{self.model_id}/invoke"
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.bearer_token}",
            }
            
            # Make the HTTP request
            response = requests.post(
                endpoint_url,
                data=body,
                headers=headers,
                timeout=60,
            )
            
            # Check for errors
            response.raise_for_status()
            
            # Parse response
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Bearer Token invoke_model request failed: {type(e).__name__}: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error response: {error_detail}")
                    
                    # Check if error is about unsupported model with on-demand throughput
                    error_message = error_detail.get("message", "")
                    if "on-demand throughput isn't supported" in error_message or "inference profile" in error_message.lower():
                        logger.warning(
                            f"Model {self.model_id} is not supported with Bearer Token API. "
                            f"Bearer Token API requires an inference profile ID, not a direct model ID. "
                            f"Consider using a model from .env.local (BEDROCK_MODEL_ID) or an inference profile ID."
                        )
                        # If we have a different model in .env.local and current model was from CLI, suggest using it
                        if self._env_model_id and self._env_model_id != self.model_id:
                            logger.info(
                                f"Note: BEDROCK_MODEL_ID in .env.local is '{self._env_model_id}', "
                                f"which might work better with Bearer Token API. "
                                f"Try removing --model-id to use the .env.local model."
                            )
                except:
                    logger.error(f"Error response text: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Bearer Token invoke_model error: {type(e).__name__}: {str(e)}")
            return None

    def invoke(
        self,
        prompt_template: str,
        variables: dict[str, Any],
        output_schema: type[T],
        max_retries: int = 1,
        call_type: str = "LLM",
    ) -> T | None:
        """
        Invoke Bedrock model with prompt and validate JSON output.

        Args:
            prompt_template: Prompt template string
            variables: Variables to substitute in template
            output_schema: Pydantic schema for output validation
            max_retries: Maximum retry attempts (default 1)
            call_type: Type of LLM call for logging (e.g., "Tool Router", "FedRAMP Mapper")

        Returns:
            Validated output or None if failed
        """
        if not self.client:
            logger.warning(f"{call_type}: LLM client not initialized")
            return None

        logger.info(f"{call_type}: Invoking LLM with schema {output_schema.__name__}")

        # Format prompt with variables
        prompt = self._format_prompt(prompt_template, variables)

        # Add JSON output instruction to user prompt
        user_prompt = prompt + "\n\nIMPORTANT: Output JSON only, no markdown, no code blocks."

        # System prompt for JSON format enforcement
        system_prompt = "You are a helpful assistant that outputs only valid JSON. Never include markdown code blocks, explanations, or any text outside the JSON object."

        for attempt in range(max_retries + 1):
            try:
                # On retry, add schema fix prompt
                if attempt > 0:
                    logger.warning(f"{call_type}: Retry attempt {attempt}/{max_retries} (previous attempt failed validation)")
                    schema_fix = f"\n\nThe expected JSON schema is: {output_schema.model_json_schema()}. Please output ONLY valid JSON matching this schema, with no additional text."
                    user_prompt_with_schema = user_prompt + schema_fix
                else:
                    user_prompt_with_schema = user_prompt

                # Call LLM
                result = self.call_llm_text(
                    system_prompt=system_prompt, user_prompt=user_prompt_with_schema
                )

                if not result:
                    logger.warning(f"{call_type}: LLM call returned no result (attempt {attempt + 1})")
                    continue

                # Log full response for debugging
                logger.debug(f"{call_type}: Full LLM response text:\n{result.text}")

                # Extract JSON from response
                json_str = self._extract_json(result.text)
                if not json_str:
                    logger.warning(f"{call_type}: Could not extract JSON from response (attempt {attempt + 1})")
                    continue

                logger.debug(f"{call_type}: Extracted JSON:\n{json_str}")

                # Parse and validate with Pydantic
                data = json.loads(json_str)
                validated = output_schema.model_validate(data)

                # Store metadata for metrics (we'll pass this through the pipeline)
                validated._llm_metadata = {
                    "latency_seconds": result.latency_seconds,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                }

                logger.info(
                    f"{call_type}: Successfully validated response (attempt {attempt + 1}, "
                    f"latency={result.latency_seconds:.2f}s, "
                    f"tokens={result.input_tokens or 'N/A'}/{result.output_tokens or 'N/A'})"
                )

                return validated

            except json.JSONDecodeError as e:
                logger.warning(f"{call_type}: JSON decode error (attempt {attempt + 1}): {str(e)}")
                if attempt < max_retries:
                    continue
            except Exception as e:
                logger.error(f"{call_type}: Validation error (attempt {attempt + 1}): {type(e).__name__}: {str(e)}")
                if attempt < max_retries:
                    continue

        logger.error(f"{call_type}: Failed after {max_retries + 1} attempts")
        return None

    def _format_prompt(self, template: str, variables: dict[str, Any]) -> str:
        """Format prompt template with variables."""
        prompt = template
        # for key, value in variables.items():
        #     prompt = prompt.replace(f"{{{key}}}", str(value))
        
        prompt = prompt.replace("{{ user_request }}", variables.get("user_request", ""))
        prompt = prompt.replace("{{ tools_text }}", variables.get("tools_text", ""))
        prompt = prompt.replace("{{ gap_title }}", variables.get("gap_title", ""))
        prompt = prompt.replace("{{ gap_description }}", variables.get("gap_description", ""))
        prompt = prompt.replace("{{ findings_summary }}", variables.get("findings_summary", ""))
        prompt = prompt.replace("{{ report_summary }}", variables.get("report_summary", ""))
        
        # Only log prompt length, not the full prompt (too verbose)
        logger.debug(f"Formatted prompt (length={len(prompt)} chars)")
        return prompt

    def _extract_json(self, text: str) -> str | None:
        """Extract JSON from text response."""
        # Try to find JSON in the response
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) > 1:
                # Remove first and last line (code block markers)
                text = "\n".join(lines[1:-1])

        # Try to find JSON object
        start_idx = text.find("{")
        end_idx = text.rfind("}")

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return text[start_idx : end_idx + 1]

        return None

    def router(self, human_request: str | None, repo_context: str) -> RouterOutput | None:
        """Call router prompt to determine scan plan (legacy)."""
        logger.info(f"Legacy Router: Processing request: {human_request or 'General security assessment'}")
        prompt_template = load_prompt("router.md")
        variables = {
            "human_request": human_request or "General security assessment",
            "repo_context": repo_context,
        }
        return self.invoke(prompt_template, variables, RouterOutput, call_type="Legacy Router")

    def tool_router(self, human_request: str | None) -> ToolRouterOutput | None:
        """
        Call tool router prompt to select scanning tools based on user request.

        Args:
            human_request: Human request describing what they want to find

        Returns:
            ToolRouterOutput with selected tools and rationale, or None if failed
        """
        if not human_request:
            # If no request, use fallback
            fallback_tool = get_fallback_tool()
            return ToolRouterOutput(
                selected_tools=[fallback_tool],
                fallback_used=True,
                rationale="No user request provided, using general fallback tool",
                tool_intent_summary="General security assessment",
            )

        # Load tool router prompt
        prompt_template = load_prompt("tool_router.md")

        # Format tool catalog for prompt
        catalog = get_tool_catalog()
        tools_text = ""
        for tool in catalog:
            tools_text += f"### {tool.display_name} (tool_id: {tool.tool_id})\n\n"
            tools_text += f"**Short Description:** {tool.short_description}\n\n"
            tools_text += f"**Detailed Description:** {tool.detailed_description}\n\n"
            tools_text += "**Strengths:**\n"
            for strength in tool.strengths:
                tools_text += f"- {strength}\n"
            tools_text += "\n**Limitations:**\n"
            for limitation in tool.limitations:
                tools_text += f"- {limitation}\n"
            tools_text += "\n**Best For:**\n"
            for use_case in tool.best_for:
                tools_text += f"- {use_case}\n"
            tools_text += f"\n**Keywords:** {', '.join(tool.keywords)}\n\n"
            tools_text += f"**Is Fallback Tool:** {'Yes' if tool.is_general_fallback else 'No'}\n\n"
            tools_text += "---\n\n"

        variables = {
            "user_request": human_request,
            "tools": catalog,  # Pass for template formatting
            "tools_text": tools_text,  # Pre-formatted text
        }

        # Call LLM for tool selection
        logger.info(f"Tool Router: Analyzing request: {human_request}")
        result = self.invoke(prompt_template, variables, ToolRouterOutput, max_retries=1, call_type="Tool Router")
        if not result:
            # LLM call failed, use deterministic fallback
            logger.warning("Tool Router: LLM call failed, using deterministic fallback")
            fallback_tool = get_fallback_tool()
            return ToolRouterOutput(
                selected_tools=[fallback_tool],
                fallback_used=True,
                rationale="LLM tool router failed, using deterministic fallback",
                tool_intent_summary=human_request[:100] if human_request else "General assessment",
            )
        
        logger.info(f"Tool Router: Selected tools: {result.selected_tools}, fallback_used={result.fallback_used}")

        # Validate and apply deterministic fallback rules
        validated_tools = self._validate_and_fallback_tools(result.selected_tools)
        fallback_applied = len(validated_tools) != len(result.selected_tools) or (
            validated_tools == [get_fallback_tool()] and not result.selected_tools
        )

        # Update result with validated tools and fallback flag
        return ToolRouterOutput(
            selected_tools=validated_tools,
            fallback_used=result.fallback_used or fallback_applied,
            rationale=result.rationale
            if not fallback_applied
            else f"{result.rationale} (Note: fallback applied for invalid tools)",
            tool_intent_summary=result.tool_intent_summary,
        )

    def _validate_and_fallback_tools(self, tool_ids: list[str]) -> list[str]:
        """
        Validate tool IDs and apply deterministic fallback.

        Args:
            tool_ids: List of tool IDs from LLM

        Returns:
            Validated list of tool IDs (never empty, always includes at least fallback)
        """
        valid_tools = {"terraform_validate", "tfsec", "checkov"}
        catalog = get_tool_catalog()
        catalog_ids = {tool.tool_id for tool in catalog}

        # Filter to only valid tool IDs from catalog
        validated = [tid for tid in tool_ids if tid in valid_tools and tid in catalog_ids]

        # If empty or invalid, use fallback
        if not validated:
            return [get_fallback_tool()]

        return validated

    def map_fedramp(self, gap_title: str, gap_description: str) -> FedRampMapperOutput | None:
        """Call FedRAMP mapper prompt."""
        logger.info(f"FedRAMP Mapper: Mapping gap: {gap_title}")
        prompt_template = load_prompt("fedramp_mapper.md")
        variables = {
            "gap_title": gap_title,
            "gap_description": gap_description,
        }
        result = self.invoke(prompt_template, variables, FedRampMapperOutput, call_type="FedRAMP Mapper")
        if result:
            logger.info(f"FedRAMP Mapper: Mapped to families: {result.families}, priority: {result.priority}")
        return result

    def remediation_advisor(
        self, gap_title: str, gap_description: str, findings_summary: str
    ) -> RemediationAdvisorOutput | None:
        """Call remediation advisor prompt."""
        logger.info(f"Remediation Advisor: Generating checklist for gap: {gap_title}")
        prompt_template = load_prompt("remediation_advisor.md")
        variables = {
            "gap_title": gap_title,
            "gap_description": gap_description,
            "findings_summary": findings_summary,
        }
        result = self.invoke(prompt_template, variables, RemediationAdvisorOutput, call_type="Remediation Advisor")
        if result:
            logger.info(
                f"Remediation Advisor: Generated {len(result.checklist)} steps, "
                f"confidence={result.overall_confidence:.2f}, "
                f"requires_human={result.requires_human_decision}"
            )
        return result

    def summary_writer(
        self, report_summary: str
    ) -> tuple[str, float, int | None, int | None] | None:
        """
        Call summary writer prompt (returns plain text, not JSON).

        Returns:
            Tuple of (summary_text, latency_seconds, input_tokens, output_tokens) or None
        """
        logger.info("Summary Writer: Generating executive summary")
        if not self.client:
            logger.warning("Summary Writer: LLM client not initialized")
            return None

        prompt_template = load_prompt("summary_writer.md")
        prompt = prompt_template.replace("{{ report_summary }}", report_summary)

        result = self.call_llm_text(user_prompt=prompt)
        if result:
            logger.info(
                f"Summary Writer: Generated summary (length={len(result.text)} chars, "
                f"latency={result.latency_seconds:.2f}s)"
            )
            logger.debug(f"Summary Writer: Summary preview: {result.text[:200]}...")
            return (
                result.text,
                result.latency_seconds,
                result.input_tokens,
                result.output_tokens,
            )
        logger.warning("Summary Writer: Failed to generate summary")
        return None
