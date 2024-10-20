import streamlit as st
import openai
import fal_client
import asyncio
import os
import time
import itertools
import requests
from PIL import Image
from io import BytesIO
from datetime import datetime
from dotenv import dotenv_values

def tune_prompt_with_openai(prompt, model):
    
    client = openai.OpenAI(secrets["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are an advanced AI assistant specialized in refining and enhancing image generation prompts. Your goal is to help users create more effective, detailed, and creative prompts for high-quality images. Respond with: 1) An improved prompt (prefix with 'PROMPT:'), 2) Explanation of changes (prefix with 'EXPLANATION:'), and 3) Additional suggestions (prefix with 'SUGGESTIONS:'). Each section should be on a new line."
            },
            {
                "role": "user",
                "content": f"Improve this image generation prompt: {prompt}"
            }
        ]
    )
    return response.choices[0].message.content.strip()

async def generate_image_with_fal(prompt, model, image_size, num_inference_steps, guidance_scale, num_images, safety_tolerance):
    FAL_KEY = secrets["FAL_KEY"]
    os.environ['FAL_KEY'] = FAL_KEY
    if not FAL_KEY:
        raise ValueError("FAL_KEY environment variable is not set")
  # Set the API key as an environment variable
    
    handler = await fal_client.submit_async(
        model,
        arguments={
            "prompt": prompt,
            "image_size": image_size,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "num_images": num_images,
            "safety_tolerance": safety_tolerance
        }
    )

    # Wait for the actual result instead of returning immediately
    result = await handler.get()
    return result

def cycle_spinner_messages():
    messages = [
        "🎨 Mixing colors...",
        "✨ Sprinkling creativity dust...",
        "🖌️ Applying artistic strokes...",
        "🌈 Infusing with vibrant hues...",
        "🔍 Focusing on details...",
        "🖼️ Framing the masterpiece...",
        "🌟 Adding that special touch...",
        "🎭 Bringing characters to life...",
        "🏙️ Building the scene...",
        "🌅 Setting the perfect mood...",
    ]
    return itertools.cycle(messages)

async def run_with_spinner(generation_coroutine, spinner_placeholder, message_cycle):
    task = asyncio.create_task(generation_coroutine)
    while not task.done():
        spinner_placeholder.text(next(message_cycle))
        await asyncio.sleep(3)
    return await task

def accept_tuned_prompt():
    st.session_state.user_prompt = st.session_state.tuned_prompt
    st.session_state.prompt_accepted = True

def format_markdown(prompt, result, model, image_size, num_inference_steps, guidance_scale, safety_tolerance):
    markdown = f"""# Image Generation Results

## Prompt
{prompt}

## Generation Details
- **Date and Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **Model:** {model}
- **Seed:** {result.get('seed', 'Not specified')}
- **NSFW Concepts Detected:** {result.get('has_nsfw_concepts', 'Not specified')}
- **Image Size:** {image_size}
- **Number of Inference Steps:** {num_inference_steps}
- **Guidance Scale:** {guidance_scale}
- **Safety Tolerance:** {safety_tolerance}

## Image URL
{result['images'][0]['url'] if 'images' in result and result['images'] else 'No image URL available'}

"""
    return markdown

def save_image_and_markdown(url, prompt, result, model, image_size, num_inference_steps, guidance_scale, safety_tolerance):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            
            # Create a filename using the current date and time
            timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
            
            # Sanitize the prompt to create a valid filename
            safe_prompt = "".join(c for c in prompt if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_prompt = safe_prompt[:50]  # Limit the length of the prompt in the filename
            
            filename_base = f"{timestamp}_{safe_prompt}"
            
            # Ensure the images directory exists
            images_folder = os.path.join(os.path.dirname(__file__), 'images')
            os.makedirs(images_folder, exist_ok=True)
            
            # Save the image
            image_filename = f"{filename_base}.png"
            full_image_path = os.path.join(images_folder, image_filename)
            image.save(full_image_path)
            
            # Save the Markdown data
            markdown_filename = f"{filename_base}.md"
            full_markdown_path = os.path.join(images_folder, markdown_filename)
            markdown_content = format_markdown(prompt, result, model, image_size, num_inference_steps, guidance_scale, safety_tolerance)
            with open(full_markdown_path, 'w', encoding='utf-8') as md_file:
                md_file.write(markdown_content)
            
            # Verify that the Markdown file is not empty
            if os.path.getsize(full_markdown_path) == 0:
                raise IOError("Markdown file is empty after writing")
            
            return full_image_path, full_markdown_path
        else:
            raise IOError(f"Failed to download image. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error in save_image_and_markdown: {str(e)}")
        return None, None

def main():
    st.title("🤖 Image Generation with fal.ai & Flux")
    secrets = st.secrets
    FAL_KEY = secrets["FAL_KEY"]
    os.environ['FAL_KEY'] = FAL_KEY

    # Check for environment variables
    if not os.getenv("FAL_KEY"):
        st.error("FAL_KEY environment variable is not set. Please set it before running the app.")
        return

    # Model selection dropdown
    model_options = {
        "Flux Pro": "fal-ai/flux-pro",
        "Flux Dev": "fal-ai/flux/dev",
        "Flux Schnell": "fal-ai/flux/schnell",
        "Flux Realism": "fal-ai/flux-realism"
    }
    selected_model = st.selectbox("Select Model:", list(model_options.keys()), index=0)

    # Basic parameters
    image_size = st.selectbox("Image Size:", ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"], index=0)
    num_inference_steps = st.slider("Number of Inference Steps:", min_value=1, max_value=50, value=28)

    # Advanced configuration in an expander
    with st.expander("Advanced Configuration", expanded=False):
        guidance_scale = st.slider("Guidance Scale:", min_value=1.0, max_value=20.0, value=3.5, step=0.1)
        safety_tolerance = st.selectbox("Safety Tolerance:", ["1", "2", "3", "4"], index=1)

    # Initialize session state
    if 'user_prompt' not in st.session_state:
        st.session_state.user_prompt = ""
    if 'tuned_prompt' not in st.session_state:
        st.session_state.tuned_prompt = ""
    if 'prompt_accepted' not in st.session_state:
        st.session_state.prompt_accepted = False

    # User input for the prompt
    user_prompt = st.text_input("Enter your image prompt:", value=st.session_state.user_prompt)

    # Update session state when user types in the input field
    if user_prompt != st.session_state.user_prompt:
        st.session_state.user_prompt = user_prompt
        st.session_state.prompt_accepted = False

    # OpenAI prompt tuning options
    use_openai_tuning = st.checkbox("Use OpenAI for prompt tuning", value=False)
    
    openai_model_options = ["gpt-4o", "gpt-4o-mini"]
    selected_openai_model = st.selectbox("Select OpenAI Model:", openai_model_options, index=0, disabled=not use_openai_tuning)

    if use_openai_tuning and user_prompt:
        os.environ['OPENAI_API_KEY'] = secrets["OPENAI_API_KEY"]
        if not os.getenv("OPENAI_API_KEY"):
            st.error("OPENAI_API_KEY environment variable is not set. Please set it before using OpenAI tuning.")
        else:
            if st.button("✏️ Tune Prompt"):
                with st.spinner("Tuning prompt with OpenAI..."):
                    try:
                        tuned_result = tune_prompt_with_openai(user_prompt, selected_openai_model)
                        
                        # Split the result into prompt, explanation, and suggestions
                        sections = tuned_result.split('\n')
                        for section in sections:
                            if section.startswith("PROMPT:"):
                                st.session_state.tuned_prompt = section.replace("PROMPT:", "").strip()
                            elif section.startswith("EXPLANATION:"):
                                explanation = section.replace("EXPLANATION:", "").strip()
                            elif section.startswith("SUGGESTIONS:"):
                                suggestions = section.replace("SUGGESTIONS:", "").strip()
                        
                        # Display the tuned prompt
                        st.subheader("Tuned Prompt:")
                        st.write(st.session_state.tuned_prompt)
                        
                        # Display explanation and suggestions in an expander
                        with st.expander("See explanation and suggestions"):
                            st.write("Explanation of changes:")
                            st.write(explanation)
                            st.write("Additional suggestions:")
                            st.write(suggestions)
                        
                        # Allow user to accept or regenerate the tuned prompt
                        col1, col2 = st.columns(2)
                        with col1:
                            st.button("✅ Accept Tuned Prompt", on_click=accept_tuned_prompt)
                        with col2:
                            if st.button("♻️ Regenerate Prompt"):
                                st.rerun()
                    except Exception as e:
                        st.error(f"Error tuning prompt: {str(e)}")

    if st.session_state.prompt_accepted:
        st.success("👍 Tuned prompt accepted and updated in the input field.")

    if st.button("☁️ Generate Image"):
        if not user_prompt:
            st.warning("⛔️ Please enter a prompt for image generation.")
            return

        # Display the prompt being used
        st.subheader("☁️ Generating image with the following prompt:")
        st.info(user_prompt)

        # Generate image with fal.ai
        try:
            spinner_placeholder = st.empty()
            message_cycle = cycle_spinner_messages()

            async def generate_image_task():
                return await generate_image_with_fal(
                    user_prompt, model_options[selected_model],
                    image_size, num_inference_steps, guidance_scale, num_images=1, safety_tolerance=safety_tolerance
                )

            async def run_with_spinner(generation_coroutine):
                task = asyncio.create_task(generation_coroutine)
                while not task.done():
                    spinner_placeholder.text(next(message_cycle))
                    await asyncio.sleep(3)
                return await task

            # Run the asynchronous code within the synchronous Streamlit environment
            result = asyncio.run(run_with_spinner(generate_image_task()))

            spinner_placeholder.empty()  # Clear the spinner

            # Display the generated image and save it along with Markdown data
            st.subheader("🖼️ Your Generated Masterpiece:")
            image_info = result['images'][0]  # We know there's only one image
            st.image(image_info['url'], caption="Generated Image", use_column_width=True)

            # Display additional information
            st.write(f"🌱 Seed: {result['seed']}")
            st.write(f"🚫 NSFW concepts detected: {result['has_nsfw_concepts']}")
            
            # Save the image and Markdown data
            saved_image_path, saved_markdown_path = save_image_and_markdown(
                image_info['url'], 
                user_prompt, 
                result, 
                selected_model, 
                image_size, 
                num_inference_steps, 
                guidance_scale, 
                safety_tolerance
            )
            if saved_image_path and saved_markdown_path:
                st.success(f"Image saved to {saved_image_path}")
                st.success(f"Generation details saved to {saved_markdown_path}")
                
                # Display the content of the Markdown file
                with open(saved_markdown_path, 'r', encoding='utf-8') as md_file:
                    markdown_content = md_file.read()
                st.markdown(markdown_content)
            else:
                st.error("Failed to save the image and/or generation details")
            
        except Exception as e:
            st.error(f"⛔️ Error generating image: {str(e)}")
            print(f"Error details: {e}")  # This will appear in your console/logs

if __name__ == "__main__":
    secrets = st.secrets
    main()
