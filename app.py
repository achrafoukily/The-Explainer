import streamlit as st
import json
import io
import os
from typing import List, Dict, Any
from docx import Document
from openai import OpenAI
import subprocess

# Initialize the client once at the top level
client = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key="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"
)

SYSTEM_PROMPT = """You are an elite Educational Curriculum Architect. 
Your architecture is a state machine with two phases. You must output your response STRICTLY as a valid JSON object on every single turn. Never output markdown outside of the JSON block.

### PHASE 1: Basic Information Gathering (State: "questioning")
When the user provides a raw topic, you need basic context to generate an educational lesson. To proceed, you just need a general idea of:
1. Target Audience (e.g., kids, adults, professionals)
2. Desired Tone or Focus (e.g., fun, academic, theory, history)

If this information is missing, you must ask EXACTLY 2 simple, general questions in a single message. Do NOT be Socratic, do NOT ask deep questions, and do not ask too many questions. Keep it brief and surface-level.
Output Schema for Phase 1:
{
  "status": "questioning",
  "message_to_user": "[A single conversational message containing exactly 2 simple, general questions asking for the basic context]"
}

### PHASE 2: Prompt Structuring & Lesson Generation (State: "complete")
Once the user has provided the necessary context (or answered your 2 questions), silently simulate the following agentic workflow:
1. Create a structured, optimized Master Prompt based on the gathered information.
2. Generate a comprehensive "Explanation Lesson", fully structured with headings and pedagogical breakdowns.
3. Fact-check the lesson internally and distill it into a strict JSON array of verified facts.
4. Write a "Narrative Monologue" script based on the fact-checked lesson, formatted specifically for pacing in a TTS voiceover.

Output Schema for Phase 2:
{
  "status": "complete",
  "optimized_prompt": "[The structured master prompt you built internally]",
  "explanation_document": "[The highly detailed, comprehensive markdown educational lesson]",
  "structured_facts": [
    {"concept": "string", "definition": "string", "fact_checked": true}
  ],
  "narrative_monologue": "[A continuous string of text meant to be read aloud by an AI voiceover]"
}"""

def hide_streamlit_style() -> None:
    """Injects custom CSS to hide the Streamlit menu and footer."""
    hide_style = """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        </style>
        """
    st.markdown(hide_style, unsafe_allow_html=True)

def llm_call(messages: List[Dict[str, str]], use_system_prompt: bool = True) -> str:
    """
    Calls NVIDIA's API using the provided model.
    """
    try:
        user_message_count = sum(1 for m in messages if m["role"] == "user")
        
        if use_system_prompt:
            dynamic_prompt = SYSTEM_PROMPT
            if user_message_count > 1:
                dynamic_prompt += "\\n\\nCRITICAL SYSTEM OVERRIDE: The user has answered your questions. You MUST now proceed to Phase 2. Output ONLY a JSON with status: 'complete', generating the explanation_document and narrative_monologue. DO NOT ask any more questions."
                
            api_messages = [{"role": "system", "content": dynamic_prompt}] + messages
        else:
            api_messages = messages
            
        completion = client.chat.completions.create(
          model="meta/llama-3.2-11b-vision-instruct",
          messages=api_messages,
          temperature=0.5,
          top_p=1,
          max_tokens=4000,
          stream=False,
          timeout=120
        )
        return completion.choices[0].message.content
    except Exception as e:
        st.error(f"API Error: {e}")
        # Fallback in case of timeout or error
        return json.dumps({
            "status": "error",
            "message_to_user": f"An error occurred: {e}"
        })

def parse_llm_response(response_text: str) -> Dict[str, Any]:
    """
    Parses the JSON response from the LLM, handling potential markdown wrappers or conversational filler.
    """
    try:
        # Isolate the JSON object by finding the first '{' and the last '}'
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            clean_json = response_text[start_idx:end_idx+1]
        else:
            clean_json = response_text
            
        return json.loads(clean_json, strict=False)
    except json.JSONDecodeError as e:
        import ast
        try:
            # Fallback 1: literal_eval handles single quotes, trailing commas, and unescaped newlines easily
            clean_json_fixed = clean_json.replace("true", "True").replace("false", "False").replace("null", "None")
            parsed = ast.literal_eval(clean_json_fixed)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
            
        # Fallback 2: Silent recovery. The user doesn't want to see red errors ever again.
        return {
            "status": "questioning",
            "message_to_user": "*(System hiccup parsing the AI's internal thought process. Continuing naturally)* Could you expand a bit more on what you want the lesson to focus on?"
        }

def init_session_state() -> None:
    if "phase" not in st.session_state:
        st.session_state.phase = 1
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "lesson_data" not in st.session_state:
        st.session_state.lesson_data = None

def render_chat_interface() -> None:
    st.title("🎓 AI Educational Curriculum Architect")
    st.subheader("Phase 1: Basic Information Gathering")

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle user input
    if prompt := st.chat_input("Enter your topic to begin..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("Analyzing request..."):
            llm_response_text = llm_call(st.session_state.messages)
            data = parse_llm_response(llm_response_text)

            if data.get("status") == "questioning":
                assistant_msg = data.get("message_to_user", "Could you elaborate?")
                st.session_state.messages.append({"role": "assistant", "content": assistant_msg})
                with st.chat_message("assistant"):
                    st.markdown(assistant_msg)
                    st.rerun()
            
            elif data.get("status") == "complete":
                st.session_state.lesson_data = data
                st.session_state.phase = "complete_ui"
                st.rerun()
            
            elif data.get("status") == "error":
                st.error(data.get("message_to_user", "Unknown API error occurred."))

def render_completion_dashboard() -> None:
    st.title("🎓 AI Educational Curriculum Architect")
    
    data = st.session_state.lesson_data
    if not data:
        st.error("No lesson data found!")
        if st.button("Restart"):
            st.session_state.phase = 1
            st.rerun()
        return

    lesson_text = data.get("explanation_document", "No explanation generated.")
    monologue = data.get("narrative_monologue", "No monologue generated.")
    
    # 1. Create the Word Document in memory
    doc = Document()
    doc.add_heading('Explanation Document', 0)
    doc.add_paragraph(lesson_text)
    
    # Save the document to a byte buffer instead of the hard drive
    bio = io.BytesIO()
    doc.save(bio)
    
    # 2. Display the UI for Phase 1 completion
    st.success("Phase 1 Complete: Lesson and Monologue Generated!")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📚 Lesson Document")
        st.markdown(lesson_text)
        
        # Provide the real .docx file to the user
        st.download_button(
            label="Download Lesson as .docx",
            data=bio.getvalue(),
            file_name="Lesson_Explanation.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
    with col2:
        st.subheader("🎙️ TTS Monologue")
        st.info(monologue)
        
        # Save monologue to disk for Phase 2's TTS engine to pick up
        try:
            with open("monologue.txt", "w", encoding="utf-8") as f:
                f.write(monologue)
            st.success("Saved monologue.txt locally.")
        except Exception as e:
            st.error(f"Failed to save monologue.txt: {e}")
            
    # Move to Phase 2
    if st.button("Proceed to Phase 2: Video Generation"):
        st.session_state.phase = 2
        st.rerun()

def render_phase_2() -> None:
    st.title("🎥 Phase 2: Manim-Style Typography Explainer")
    
    if not os.path.exists("monologue.txt"):
        st.error("monologue.txt not found! Please complete Phase 1 first.")
        if st.button("Restart"):
            st.session_state.clear()
            init_session_state()
            st.rerun()
        return

    st.info("Generating typography animation (Manim Style)...")
    
    with open("monologue.txt", "r", encoding="utf-8") as f:
        monologue = f.read()

    # 1. Generate TTS
    with st.spinner("Generating Text-to-Speech audio..."):
        try:
            subprocess.run(
                ["npx", "--yes", "hyperframes@0.8.80", "tts", "monologue.txt", "-o", "narration.wav"], 
                check=True, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            st.error(f"Failed to generate TTS:\nSTDOUT:\n{e.stdout.decode()}\nSTDERR:\n{e.stderr.decode()}")
            return
            
    # 2. Prepare HyperFrames composition (Manim style)
    with st.spinner("Assembling Typography Composition..."):
        try:
            import re
            
            # Get actual audio duration
            audio_duration = 15.0
            try:
                result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                         "format=duration", "-of",
                                         "default=noprint_wrappers=1:nokey=1", "narration.wav"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
                audio_duration = float(result.stdout)
            except Exception:
                pass
            
            # Split into phrases and calculate timings
            phrases_raw = re.split(r'(?<=[.?!,;])\s+', monologue.strip())
            total_chars = sum(len(p) for p in phrases_raw)
            current_time = 0.1 # slight start offset
            
            html_phrases = []
            gsap_animations = []
            
            for i, phrase in enumerate(phrases_raw):
                if not phrase: continue
                phrase_duration = (len(phrase) / max(total_chars, 1)) * audio_duration
                
                words = phrase.split()
                phrase_chars = sum(len(w) for w in words)
                
                html_words = []
                phrase_current = current_time
                for j, word in enumerate(words):
                    word_duration = (len(word) / max(phrase_chars, 1)) * phrase_duration
                    highlight_class = "highlight" if (len(word) > 7) else ""
                    html_words.append(f'<span class="word {highlight_class}" id="w_{i}_{j}">{word}</span>')
                    
                    # Word appears
                    gsap_animations.append(f"tl.to('#w_{i}_{j}', {{ opacity: 1, duration: 0.15 }}, {phrase_current});")
                    phrase_current += word_duration
                    
                html_phrases.append(f'<div class="phrase" id="p_{i}">{" ".join(html_words)}</div>')
                # Phrase disappears at the end of its duration
                gsap_animations.append(f"tl.to('#p_{i}', {{ opacity: 0, duration: 0.2 }}, {current_time + phrase_duration});")
                
                current_time += phrase_duration

            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="https://unpkg.com/gsap@3.12.5/dist/gsap.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Computer+Modern+Serif&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        body {{ 
            margin: 0; background: #1e1e1e; color: #dcdcdc; 
            font-family: 'Lora', serif; display: flex;
            align-items: center; justify-content: center;
        }}
        #root {{ 
            width: 100%; height: 100%; position: relative; overflow: hidden;
            display: flex; align-items: center; justify-content: center;
            padding: 100px; box-sizing: border-box;
        }}
        #text-container {{
            font-size: 72px; line-height: 1.5; text-align: center; max-width: 1600px;
            position: relative; width: 100%; height: 100%;
            display: flex; align-items: center; justify-content: center;
        }}
        .phrase {{
            position: absolute;
            width: 100%;
        }}
        .word {{
            display: inline-block;
            opacity: 0; /* Hidden initially */
            margin-right: 18px;
            text-shadow: 0 4px 15px rgba(0,0,0,0.5);
        }}
        .highlight {{
            color: #58C4DD; font-style: italic;
        }}
    </style>
</head>
<body>
    <div id="root" data-composition-id="main" data-width="1920" data-height="1080" data-duration="15">
        <!-- Master Audio Track -->
        <audio id="narration" src="narration.wav" data-start="0"></audio>
        
        <div class="clip" data-start="0">
            <div id="text-container">
                {"".join(html_phrases)}
            </div>
        </div>
    </div>
    <script>
        const tl = gsap.timeline({{ paused: true }});
        {"".join(gsap_animations)}
        window.__timelines = window.__timelines || {{}};
        window.__timelines["main"] = tl;
    </script>
</body>
</html>"""
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception as e:
            st.error(f"Failed to prepare composition: {e}")
            return

    # 3. Render Video
    with st.spinner("Rendering final Manim-style explainer video..."):
        try:
            subprocess.run(
                ["npx", "--yes", "hyperframes@0.8.80", "render", "--quality", "draft", "--output", "final_typography.mp4"], 
                check=True, capture_output=True
            )
            st.success("Typography Video rendered successfully!")
            st.video("final_typography.mp4")
            
        except subprocess.CalledProcessError as e:
            st.error(f"Failed to render video:\nSTDOUT:\n{e.stdout.decode()}\nSTDERR:\n{e.stderr.decode()}")
            return

    if st.button("Restart"):
        st.session_state.clear()
        init_session_state()
        st.rerun()

def main() -> None:
    st.set_page_config(page_title="Curriculum Architect", page_icon="🎓", layout="wide")
    hide_streamlit_style()
    init_session_state()

    if st.session_state.phase == 1:
        render_chat_interface()
    elif st.session_state.phase == "complete_ui":
        render_completion_dashboard()
    elif st.session_state.phase == 2:
        render_phase_2()

if __name__ == "__main__":
    main()
