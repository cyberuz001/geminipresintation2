import os
import logging
import time
import asyncio
import random
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
import google.generativeai as genai
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get API keys from environment variables
api_keys = []
main_api_key = os.getenv("GEMINI_API_KEY")
if main_api_key:
    api_keys.append(main_api_key)

# Check for additional API keys (GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc.)
i = 1
while True:
    key = os.getenv(f"GEMINI_API_KEY_{i}")
    if key:
        api_keys.append(key)
        i += 1
    else:
        break

if not api_keys:
    logger.error("No Gemini API keys found in environment variables")
else:
    logger.info(f"Loaded {len(api_keys)} Gemini API key(s)")
    # Configure with the first key initially
    genai.configure(api_key=api_keys[0])

# Function to get a random API key from the available keys
def get_random_api_key():
    if not api_keys:
        raise ValueError("No Gemini API keys available")
    return random.choice(api_keys)

# List available models to help with debugging
def list_available_models():
    try:
        models = genai.list_models()
        logger.info("Available Gemini models:")
        for model in models:
            logger.info(f"- {model.name}")
        return models
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        return []

GEMINI_COMPLETION_OPTIONS = {
    "temperature": 0.75,
    "top_p": 1,
    "max_output_tokens": 3072,
}

# Maximum number of retries for API calls
MAX_RETRIES = 3
# Base delay for exponential backoff (in seconds)
BASE_DELAY = 2
# Maximum concurrent requests - API kalitlar soniga qarab o'zgartiramiz
MAX_CONCURRENT_REQUESTS = len(api_keys) * 2 if api_keys else 3
# Semaphore to limit concurrent requests
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Request queue for managing high load
request_queue = asyncio.Queue()
# Dictionary to store results for each request
request_results: Dict[str, Any] = {}
# Flag to indicate if the queue worker is running
queue_worker_running = False
# Maximum queue size before rejecting new requests
MAX_QUEUE_SIZE = 100
# Current queue size counter
current_queue_size = 0
# Task references to keep track of background tasks
_queue_worker_task = None
_cleanup_task = None

async def process_prompt_direct(message):
    """Process a prompt with Gemini API with retry logic and rate limiting (direct call)"""
    answer = None
    retry_count = 0
    
    # Use semaphore to limit concurrent requests
    async with request_semaphore:
        while answer is None and retry_count < MAX_RETRIES:
            try:
                # Select a random API key for load balancing
                api_key = get_random_api_key()
                genai.configure(api_key=api_key)
                
                # List available models for debugging if this is the first attempt
                if retry_count == 0:
                    models = list_available_models()
                    
                    # Find the appropriate model name
                    model_name = None
                    # Try to find the best available model in this order of preference
                    preferred_models = [
                        "gemini-pro",
                        "gemini-1.5-pro",
                        "gemini-1.5-flash",
                        "gemini-2.0-flash",
                        "gemini-1.0-pro"
                    ]
                    
                    for preferred in preferred_models:
                        for model in models:
                            if preferred in model.name:
                                model_name = model.name
                                logger.info(f"Using model: {model_name}")
                                break
                        if model_name:
                            break
                    
                    if not model_name:
                        # Fallback to a default model name format
                        model_name = "models/gemini-1.5-flash"
                        logger.warning(f"No preferred model found in available models. Falling back to: {model_name}")
                else:
                    # Use the default model name for retry attempts to save time
                    model_name = "models/gemini-pro"
                
                # Initialize the Gemini model
                model = genai.GenerativeModel(model_name)
                
                # Generate content
                logger.info(f"Sending request to Gemini API (attempt {retry_count + 1}/{MAX_RETRIES})")
                start_time = time.time()
                try:
                    response = await asyncio.wait_for(
                        model.generate_content_async(
                            message,
                            generation_config=GEMINI_COMPLETION_OPTIONS
                        ),
                        timeout=90  # 90 sekund timeout
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError("API request timed out after 90 seconds")
                end_time = time.time()
                
                # Log the response time
                logger.info(f"Gemini API response received in {end_time - start_time:.2f} seconds")
                
                answer = response.text
                
                # Estimate token usage (Gemini doesn't provide this directly)
                # Rough estimate: 1 token ≈ 4 characters for English text
                n_used_tokens = len(message) // 4 + len(answer) // 4
                
                logger.info(f"Successfully generated content with estimated {n_used_tokens} tokens")
                return answer, n_used_tokens
                
            except Exception as e:
                retry_count += 1
                error_message = str(e).lower()
                logger.error(f"Error in process_prompt (attempt {retry_count}/{MAX_RETRIES}): {error_message}")
                
                # Handle specific error cases
                if "too many tokens" in error_message:
                    logger.error("Token limit exceeded error")
                    raise ValueError("Too many tokens to make completion") from e
                
                if retry_count < MAX_RETRIES:
                    # Boshqa API kalitni sinab ko'rish
                    api_key = get_random_api_key()
                    genai.configure(api_key=api_key)
                    logger.info(f"Switching to a different API key for retry {retry_count}")
                    
                    # Calculate delay with exponential backoff and jitter
                    delay = BASE_DELAY * (2 ** (retry_count - 1)) + random.uniform(0, 1)
                    logger.info(f"Retrying in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed, categorize the error
                    if "overloaded" in error_message or "rate limit" in error_message or "quota" in error_message:
                        logger.error("API overloaded or rate limit reached")
                        raise OverflowError("That model is currently overloaded with other requests.") from e
                    elif "timeout" in error_message or "deadline" in error_message:
                        logger.error("API request timed out")
                        raise TimeoutError("Request to the model timed out. Please try again.") from e
                    else:
                        logger.error(f"Unhandled API error: {error_message}")
                        raise RuntimeError(f"Error with Gemini API after {MAX_RETRIES} attempts: {str(e)}") from e

async def queue_worker():
    """Worker that processes requests from the queue"""
    global queue_worker_running, current_queue_size
    queue_worker_running = True
    
    logger.info("Starting queue worker")
    
    try:
        while True:
            try:
                # Get a request from the queue
                request_id, message, priority = await request_queue.get()
                current_queue_size -= 1
                
                logger.info(f"Processing queued request {request_id} (priority: {priority}, queue size: {current_queue_size})")
                
                try:
                    # Process the request
                    result = await process_prompt_direct(message)
                    # Store the result
                    request_results[request_id] = {
                        "status": "completed",
                        "result": result,
                        "error": None,
                        "completed_at": datetime.now().isoformat()
                    }
                    logger.info(f"Request {request_id} completed successfully")
                except Exception as e:
                    # Store the error
                    request_results[request_id] = {
                        "status": "error",
                        "result": None,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "completed_at": datetime.now().isoformat()
                    }
                    logger.error(f"Request {request_id} failed with error: {str(e)}")
                
                # Mark the task as done
                request_queue.task_done()
                
                # Add a small delay between processing requests to avoid API rate limits
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                logger.info("Queue worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in queue worker: {str(e)}")
                # Continue processing other requests
                await asyncio.sleep(1)
    finally:
        queue_worker_running = False
        logger.info("Queue worker stopped")

def start_queue_worker():
    """Start the queue worker if it's not already running"""
    global queue_worker_running, _queue_worker_task
    if not queue_worker_running and _queue_worker_task is None:
        try:
            # Check if there's a running event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Start the worker as a background task
                _queue_worker_task = loop.create_task(queue_worker())
                logger.info("Queue worker started")
            else:
                logger.warning("No running event loop, queue worker will be started when needed")
        except RuntimeError:
            logger.warning("No running event loop, queue worker will be started when needed")

async def process_prompt(message, priority=1, wait_for_result=True, timeout=120):
    """
    Process a prompt by adding it to the queue
    
    Args:
        message: The prompt message
        priority: Priority level (1-5, lower is higher priority)
        wait_for_result: Whether to wait for the result or return immediately
        timeout: Maximum time to wait for the result in seconds
        
    Returns:
        If wait_for_result is True, returns the result tuple (answer, n_used_tokens)
        If wait_for_result is False, returns the request_id
    """
    global current_queue_size, queue_worker_running, _queue_worker_task
    
    # Start the queue worker if it's not running
    if not queue_worker_running and _queue_worker_task is None:
        _queue_worker_task = asyncio.create_task(queue_worker())
        logger.info("Queue worker started on demand")
    
    # Generate a unique request ID
    request_id = f"req_{int(time.time())}_{random.randint(1000, 9999)}"
    
    # Check if the queue is full
    if current_queue_size >= MAX_QUEUE_SIZE:
        logger.warning(f"Request queue is full ({current_queue_size}/{MAX_QUEUE_SIZE})")
        raise OverflowError("Tizim hozir juda band. Iltimos, keyinroq qayta urinib ko'ring.")
    
    # Add the request to the queue
    current_queue_size += 1
    await request_queue.put((request_id, message, priority))
    
    logger.info(f"Added request {request_id} to queue (priority: {priority}, queue size: {current_queue_size})")
    
    # Initialize the result entry
    request_results[request_id] = {
        "status": "queued",
        "queued_at": datetime.now().isoformat(),
        "result": None,
        "error": None
    }
    
    if not wait_for_result:
        # Return the request ID immediately
        return request_id
    
    # Wait for the result
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Check if the result is ready
        if request_id in request_results and request_results[request_id]["status"] in ["completed", "error"]:
            result_data = request_results[request_id]
            
            # Clean up the result to save memory
            del request_results[request_id]
            
            if result_data["status"] == "error":
                # Raise the appropriate exception
                error_type = result_data.get("error_type", "RuntimeError")
                error_message = result_data.get("error", "Unknown error")
                
                if error_type == "ValueError":
                    raise ValueError(error_message)
                elif error_type == "OverflowError":
                    raise OverflowError(error_message)
                elif error_type == "TimeoutError":
                    raise TimeoutError(error_message)
                else:
                    raise RuntimeError(error_message)
            
            # Return the result
            return result_data["result"]
        
        # Wait a bit before checking again
        await asyncio.sleep(0.5)
    
    # Timeout reached
    logger.error(f"Request {request_id} timed out after {timeout} seconds")
    
    # Update the status
    if request_id in request_results:
        request_results[request_id]["status"] = "timeout"
    
    raise TimeoutError(f"So'rov vaqti tugadi ({timeout} soniya). Iltimos, keyinroq qayta urinib ko'ring.")

async def check_request_status(request_id):
    """Check the status of a request"""
    if request_id in request_results:
        return request_results[request_id]
    return {"status": "not_found", "error": "Request not found"}

async def get_queue_status():
    """Get the current status of the queue"""
    return {
        "queue_size": current_queue_size,
        "max_queue_size": MAX_QUEUE_SIZE,
        "worker_running": queue_worker_running,
        "pending_results": len(request_results),
        "api_keys_count": len(api_keys)
    }

# Clean up old results periodically
async def cleanup_old_results():
    """Clean up old results to prevent memory leaks"""
    while True:
        try:
            now = datetime.now()
            to_delete = []
            
            for req_id, data in request_results.items():
                # Check if the result is older than 1 hour
                if "completed_at" in data:
                    completed_time = datetime.fromisoformat(data["completed_at"])
                    if (now - completed_time).total_seconds() > 3600:  # 1 hour
                        to_delete.append(req_id)
                # Check if queued requests are older than 2 hours
                elif "queued_at" in data:
                    queued_time = datetime.fromisoformat(data["queued_at"])
                    if (now - queued_time).total_seconds() > 7200:  # 2 hours
                        to_delete.append(req_id)
            
            # Delete old results
            for req_id in to_delete:
                del request_results[req_id]
                
            if to_delete:
                logger.info(f"Cleaned up {len(to_delete)} old results")
                
            # Run every 15 minutes
            await asyncio.sleep(900)
        except Exception as e:
            logger.error(f"Error in cleanup_old_results: {str(e)}")
            await asyncio.sleep(60)

# Start the cleanup task
def start_cleanup_task():
    """Start the cleanup task"""
    global _cleanup_task
    try:
        # Check if there's a running event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _cleanup_task = loop.create_task(cleanup_old_results())
            logger.info("Cleanup task started")
        else:
            logger.warning("No running event loop, cleanup task will be started when needed")
    except RuntimeError:
        logger.warning("No running event loop, cleanup task will be started when needed")

# Initialize the system
def initialize():
    """Initialize the queue system"""
    global _queue_worker_task, _cleanup_task
    
    try:
        # Check if there's a running event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in a running event loop, create tasks
            _queue_worker_task = loop.create_task(queue_worker())
            _cleanup_task = loop.create_task(cleanup_old_results())
        else:
            # No running event loop, start a new one just for initialization
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            _queue_worker_task = new_loop.create_task(queue_worker())
            _cleanup_task = new_loop.create_task(cleanup_old_results())
            # Don't run the loop here, let the bot framework handle it
    except Exception as e:
        logger.error(f"Error initializing Gemini queue system: {e}")
    
    logger.info("Gemini queue system initialized")

# Don't initialize when the module is imported
# We'll initialize in the bot.py file when the bot starts
