import os
import uuid
from typing import Dict, List, Optional, Union, Any
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import chromadb
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import logging
import re
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ---------- FastAPI setup ----------
app = FastAPI(title="Mental Health Self-Assessment API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OpenAI & Chroma clients ----------
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
chroma_client = chromadb.PersistentClient(path=os.getenv("CHROMA_DB_PATH", "./chroma_db"))
problem_collection = chroma_client.get_or_create_collection(name="problems_collection")

# ---------- Pydantic models ----------
class StartRequest(BaseModel):
    user_input: Optional[str] = None
    problem_id: Optional[str] = None

class AnswerRequest(BaseModel):
    session_id: str
    user_answer: str

class ProblemModel(BaseModel):
    problem_id: str
    problem_name: str

class QuestionResponse(BaseModel):
    session_id: str
    question_id: str
    question_text: str
    response_type: str

class SuggestionPromptResponse(BaseModel):
    session_id: str
    suggestion_id: str
    suggestion_text: str
    resource_link: str
    prompt_id: str
    prompt_text: str

class FeedbackPromptResponse(BaseModel):
    session_id: str
    prompt_id: str
    prompt_text: str

class ConclusionResponse(BaseModel):
    session_id: str
    conclusion: str

class ConversationalResponse(BaseModel):
    session_id: str
    message: str
    message_type: str = Field(..., description="Type of message: 'general', 'question', 'suggestion', 'urgent', 'conclusion'")
    next_action: Optional[str] = Field(None, description="Suggested next action: 'continue', 'resources', 'professional_help'")
    resources: Optional[List[Dict[str, str]]] = Field(None, description="List of relevant resources")

# ---------- Constants for crisis detection ----------
CRISIS_KEYWORDS = [
    "suicid", "kill myself", "end my life", "take my life", "die", "death",
    "self-harm", "cutting myself", "hurt myself", "harming myself",
    "want to die", "not worth living", "better off dead", "no reason to live",
    "plan to kill", "method to", "overdose", "jump off", "hang myself"
]

CRISIS_RESPONSE = """
I notice you mentioned thoughts about harming yourself or suicide. Your safety is the top priority.

Please consider these immediate resources:
- National Suicide Prevention Lifeline: 988 or 1-800-273-8255 (24/7)
- Crisis Text Line: Text HOME to 741741 (24/7)
- Emergency Services: 911

Would you like me to provide more specific resources in your area?
"""

# ---------- Load Excel data ----------
def load_excel_data():
    base = Path(__file__).parent
    data_file = base.parent / "app" / "data" / "2. AI_MentalHealth_Data_Seed.xlsx"

    df_problems = pd.read_excel(data_file, sheet_name="1.1 Problems").fillna("")
    df_assessment = pd.read_excel(data_file, sheet_name="1.2 Self Assessment").fillna("")
    df_suggestions = pd.read_excel(data_file, sheet_name="1.3 Suggestions").fillna("")
    df_feedback = pd.read_excel(data_file, sheet_name="1.4 Feedback Prompts").fillna("")

    # Ensure ID columns are strings
    df_problems["problem_id"] = df_problems["problem_id"].astype(str)
    df_assessment[["problem_id", "question_id"]] = df_assessment[["problem_id", "question_id"]].astype(str)
    df_suggestions[["problem_id", "suggestion_id"]] = df_suggestions[["problem_id", "suggestion_id"]].astype(str)
    df_feedback["prompt_id"] = df_feedback["prompt_id"].astype(str)

    # Feedback prompt sequence (in sheet order)
    feedback_sequence = df_feedback["prompt_id"].tolist()

    return df_problems, df_assessment, df_suggestions, df_feedback, feedback_sequence

# Try to load Excel data
try:
    DF_PROBLEMS, DF_ASSESSMENT, DF_SUGGESTIONS, DF_FEEDBACK, FEEDBACK_SEQUENCE = load_excel_data()
    PROBLEM_LIST = DF_PROBLEMS["problem_name"].tolist()
    # Index problem embeddings
    for _, row in DF_PROBLEMS.iterrows():
        try:
            resp = openai_client.embeddings.create(model="text-embedding-3-small", input=row.problem_name)
            emb = resp.data[0].embedding
            problem_collection.upsert(
                ids=[row.problem_id],
                embeddings=[emb],
                metadatas=[{"problem_name": row.problem_name}]
            )
            logger.info(f"Indexed problem: {row.problem_id} - {row.problem_name}")
        except Exception as e:
            logger.error(f"Error indexing problem {row.problem_id}: {e}")
except Exception as e:
    logger.error(f"Error loading Excel data: {e}")
    # Provide fallback data for testing
    DF_PROBLEMS = pd.DataFrame({
        "problem_id": ["P1", "P2", "P3"],
        "problem_name": ["Anxiety", "Depression", "Stress"]
    })
    DF_ASSESSMENT = pd.DataFrame({
        "problem_id": ["P1", "P1", "P2", "P2", "P3", "P3"],
        "question_id": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"],
        "question_text": [
            "How often do you feel anxious?",
            "What triggers your anxiety?",
            "How often do you feel sad?",
            "Does it affect your daily life?",
            "What causes stress in your life?",
            "How do you cope with stress?"
        ],
        "response_type": ["text", "text", "text", "text", "text", "text"],
        "next_step": ["Q2", "end_assess", "Q4", "end_assess", "Q6", "end_assess"]
    })
    DF_SUGGESTIONS = pd.DataFrame({
        "problem_id": ["P1", "P2", "P3"],
        "suggestion_id": ["S1", "S2", "S3"],
        "suggestion_text": [
            "Try deep breathing exercises when feeling anxious.",
            "Consider keeping a mood journal to track your emotions.",
            "Regular exercise can help reduce stress."
        ],
        "resource_link": [
            "https://www.anxietyresources.org",
            "https://www.depressionresources.org",
            "https://www.stressresources.org"
        ]
    })
    DF_FEEDBACK = pd.DataFrame({
        "prompt_id": ["F1", "F2", "F3"],
        "prompt_text": [
            "How do you feel about this suggestion?",
            "Would you try this approach?",
            "What has worked for you in the past?"
        ]
    })
    FEEDBACK_SEQUENCE = ["F1", "F2", "F3"]
    PROBLEM_LIST = DF_PROBLEMS["problem_name"].tolist()

# ---------- In-memory session store ----------
# Enhanced session structure:
# {
#   problem_id: Optional[str],  # Can be None for freestyle conversations
#   current_question_id: Optional[str],
#   answers: Dict[question_id, answer],
#   stage: "assessment" | "feedback" | "conclusion" | "conversation" | "crisis",
#   suggestions_shown: List[suggestion_id],
#   feedback_step: int,
#   conversation_history: List[Dict],  # For tracking the chat for better context
#   llm_context: Dict,  # For maintaining context with the LLM
#   created_at: datetime,
#   last_activity: datetime
# }
active_sessions: Dict[str, Dict] = {}

# ---------- Helper functions ----------
def semantic_match(text: str, top_n: int = 3) -> List[Dict]:
    """Find semantically similar problems from our dataset"""
    try:
        resp = openai_client.embeddings.create(model="text-embedding-3-small", input=text)
        emb = resp.data[0].embedding
        results = problem_collection.query(query_embeddings=[emb], n_results=top_n, include=["distances", "metadatas"])

        if not results["ids"][0]:  # No matches
            return []

        recs = []
        for pid, dist, metadata in zip(results["ids"][0], results["distances"][0], results["metadatas"][0]):
            name = metadata.get("problem_name")
            if not name and pid in DF_PROBLEMS["problem_id"].values:
                name = DF_PROBLEMS.loc[DF_PROBLEMS.problem_id == pid, "problem_name"].iloc[0]
            recs.append({"problem_id": pid, "problem_name": name, "score": 1 - dist})
        return recs
    except Exception as e:
        logger.error(f"Error in semantic_match: {e}")
        return []

def detect_crisis(text: str) -> bool:
    """Check if the user's message contains crisis indicators"""
    text_lower = text.lower()
    for keyword in CRISIS_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def get_llm_response(prompt: str, history: List[Dict], temperature: float = 0.7) -> str:
    """Get a response from the LLM using the conversation history"""
    try:
        system_message = """
        You are a compassionate mental health assistant designed to provide support and guidance.
        Your responses should be:
        1. Empathetic and understanding
        2. Non-judgmental and supportive
        3. Clear and concise
        4. Tailored to the user's specific situation
        5. Evidence-based when possible

        Remember that you're not a replacement for professional mental health care.
        When appropriate, encourage seeking professional help.

        DO NOT respond with generic, template-like answers. Be conversational and genuine.
        """

        messages = [{"role": "system", "content": system_message}]
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Can be upgraded to more capable models
            messages=messages,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error getting LLM response: {e}")
        return "I'm having trouble processing that right now. Can you try phrasing your question differently?"

def analyze_user_input(text: str) -> Dict:
    """Analyze user input to determine intent and extract key information"""
    try:
        analysis_prompt = f"""
        Analyze the following user input for a mental health app:
        "{text}"

        Please provide the following information in JSON format:
        1. primary_intent: What is the main intent? (seeking_help, asking_question, providing_information, expressing_emotion, unclear)
        2. topics: What mental health topics are mentioned? (anxiety, depression, stress, etc.)
        3. emotion: What is the primary emotion expressed? (sad, anxious, angry, etc.)
        4. severity: Rate the apparent severity (1-5, where 5 is most severe)
        5. crisis_risk: Is there any indication of self-harm or harm to others? (yes/no)
        6. follow_up_needed: Does this require professional follow-up? (yes/no)
        7. recommended_approach: What approach should the app take? (structured_assessment, conversation, resources, professional_referral)
        """

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You analyze user inputs and return structured JSON only."},
                {"role": "user", "content": analysis_prompt}
            ],
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"Error analyzing user input: {e}")
        return {
            "primary_intent": "unclear",
            "topics": [],
            "emotion": "neutral",
            "severity": 1,
            "crisis_risk": "no",
            "follow_up_needed": "no",
            "recommended_approach": "conversation"
        }

def generate_resources(problem: str) -> List[Dict[str, str]]:
    """Generate relevant resources for a specific problem"""
    try:
        # First check if we have the problem in our dataset
        if problem.lower() in [p.lower() for p in PROBLEM_LIST]:
            # Use suggestions from our dataset
            matched_problem_id = DF_PROBLEMS.loc[DF_PROBLEMS.problem_name.str.lower() == problem.lower(), "problem_id"].iloc[0]
            suggestions = DF_SUGGESTIONS[DF_SUGGESTIONS.problem_id == matched_problem_id]

            if not suggestions.empty:
                return [
                    {
                        "title": f"Suggestion: {s.suggestion_text[:50]}...",
                        "description": s.suggestion_text,
                        "link": s.resource_link
                    }
                    for s in suggestions.itertuples()
                ]

        # If not found or empty, generate with LLM
        prompt = f"""
        Provide 3 helpful, evidence-based resources for someone dealing with {problem}.
        Format each resource as a JSON object with these fields:
        - title: A brief, informative title
        - description: A short description (max 150 chars)
        - link: A specific URL to a reputable website (e.g. NIMH, Mayo Clinic, etc.)

        Return only a JSON array of these resources.
        """

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You create helpful resource lists in JSON format."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        # Extract JSON array if embedded in a larger JSON object
        matches = re.search(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
        if matches:
            content = matches.group(0)

        resources = json.loads(content)
        return resources
    except Exception as e:
        logger.error(f"Error generating resources: {e}")
        return [
            {
                "title": "NIMH Mental Health Information",
                "description": "Trusted information about mental health conditions",
                "link": "https://www.nimh.nih.gov/health"
            },
            {
                "title": "Mental Health America",
                "description": "Tools and resources for various mental health issues",
                "link": "https://mhanational.org/finding-help"
            }
        ]

def clean_session_data():
    """Remove old sessions to prevent memory buildup"""
    now = datetime.now()
    expired_sessions = []

    for sid, session in active_sessions.items():
        # Remove sessions older than 24 hours or inactive for 2 hours
        if (now - session.get("created_at", now)).total_seconds() > 86400 or \
           (now - session.get("last_activity", now)).total_seconds() > 7200:
            expired_sessions.append(sid)

    for sid in expired_sessions:
        active_sessions.pop(sid, None)

    if expired_sessions:
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

# ---------- API endpoints ----------
@app.get("/problems", response_model=List[ProblemModel])
async def get_problems():
    """Get list of all predefined mental health problems"""
    return [ProblemModel(problem_id=r.problem_id, problem_name=r.problem_name)
            for r in DF_PROBLEMS.itertuples()]

@app.post("/start", response_model=ConversationalResponse)
async def start_assessment(req: StartRequest):
    """Start a new assessment session, with improved flexibility"""
    # Check if we need to run session cleanup
    if len(active_sessions) > 100:  # Arbitrary threshold
        clean_session_data()

    # Generate session ID
    sid = str(uuid.uuid4())

    # Initialize basic session
    session = {
        "problem_id": None,
        "current_question_id": None,
        "answers": {},
        "stage": "conversation",  # Default to conversational mode
        "suggestions_shown": [],
        "feedback_step": 0,
        "conversation_history": [],
        "llm_context": {},
        "created_at": datetime.now(),
        "last_activity": datetime.now()
    }

    # Handle different start cases
    if req.problem_id:
        # Direct problem selection
        if req.problem_id in DF_PROBLEMS["problem_id"].values:
            problem_name = DF_PROBLEMS.loc[DF_PROBLEMS.problem_id == req.problem_id, "problem_name"].iloc[0]

            # Set up structured assessment
            qs = DF_ASSESSMENT[DF_ASSESSMENT.problem_id == req.problem_id]
            if not qs.empty:
                first = qs.iloc[0]
                session["problem_id"] = req.problem_id
                session["current_question_id"] = first.question_id
                session["stage"] = "assessment"

                active_sessions[sid] = session

                return ConversationalResponse(
                    session_id=sid,
                    message=f"I understand you'd like to talk about {problem_name}. {first.question_text}",
                    message_type="question",
                    next_action="continue"
                )
            else:
                # No questions for this problem, use conversational approach
                welcome_msg = f"I understand you'd like to talk about {problem_name}. How has this been affecting you lately?"
                session["conversation_history"].append({"role": "assistant", "content": welcome_msg})

                active_sessions[sid] = session

                return ConversationalResponse(
                    session_id=sid,
                    message=welcome_msg,
                    message_type="general",
                    next_action="continue"
                )

    # Handle free text input
    if req.user_input:
        user_input = req.user_input.strip()

        # Check for crisis indicators first
        if detect_crisis(user_input):
            session["stage"] = "crisis"
            active_sessions[sid] = session

            return ConversationalResponse(
                session_id=sid,
                message=CRISIS_RESPONSE,
                message_type="urgent",
                next_action="professional_help",
                resources=[
                    {
                        "title": "National Suicide Prevention Lifeline",
                        "description": "24/7 support for people in distress",
                        "link": "https://988lifeline.org/"
                    },
                    {
                        "title": "Crisis Text Line",
                        "description": "Text HOME to 741741 for crisis support",
                        "link": "https://www.crisistextline.org/"
                    }
                ]
            )

        # Analyze the user input
        analysis = analyze_user_input(user_input)

        # Log the user's first message
        session["conversation_history"].append({"role": "user", "content": user_input})

        # Determine if we should use structured assessment or conversational
        if analysis["recommended_approach"] == "structured_assessment" and analysis["topics"]:
            # Try to match to known problems
            matched_problems = []
            for topic in analysis["topics"]:
                # Check exact match first
                for idx, problem in enumerate(PROBLEM_LIST):
                    if topic.lower() in problem.lower():
                        pid = DF_PROBLEMS.iloc[idx].problem_id
                        matched_problems.append((pid, problem))
                        break

            if not matched_problems and user_input:
                # Use semantic matching as fallback
                semantic_matches = semantic_match(user_input)
                if semantic_matches:
                    matched_problems = [(match["problem_id"], match["problem_name"])
                                       for match in semantic_matches]

            if matched_problems:
                pid, problem_name = matched_problems[0]  # Use top match

                # Check if we have assessment questions for this problem
                qs = DF_ASSESSMENT[DF_ASSESSMENT.problem_id == pid]
                if not qs.empty:
                    first = qs.iloc[0]
                    session["problem_id"] = pid
                    session["current_question_id"] = first.question_id
                    session["stage"] = "assessment"

                    response_msg = f"I understand you're dealing with {problem_name}. Let's talk about that. {first.question_text}"
                    session["conversation_history"].append({"role": "assistant", "content": response_msg})

                    active_sessions[sid] = session

                    return ConversationalResponse(
                        session_id=sid,
                        message=response_msg,
                        message_type="question",
                        next_action="continue"
                    )

        # Default to conversational mode
        if analysis["severity"] >= 4:
            response_msg = get_llm_response(
                f"The user has said: '{user_input}'. They seem to be in significant distress. " +
                "Respond with empathy and suggest professional help, but don't be pushy or clinical. " +
                "Keep your response under 150 words.",
                session["conversation_history"]
            )

            resources = generate_resources(analysis["topics"][0] if analysis["topics"] else "mental health support")

            session["conversation_history"].append({"role": "assistant", "content": response_msg})
            active_sessions[sid] = session

            return ConversationalResponse(
                session_id=sid,
                message=response_msg,
                message_type="general",
                next_action="resources",
                resources=resources
            )
        else:
            # Normal conversational response
            response_msg = get_llm_response(
                f"The user has said: '{user_input}'. Respond conversationally and with empathy, " +
                "asking a thoughtful follow-up question. Keep your response under 150 words.",
                session["conversation_history"]
            )

            session["conversation_history"].append({"role": "assistant", "content": response_msg})
            active_sessions[sid] = session

            return ConversationalResponse(
                session_id=sid,
                message=response_msg,
                message_type="general",
                next_action="continue"
            )

    # Fallback welcome message
    welcome_msg = "Hi there. I'm here to support you with any mental health concerns you might have. What brings you here today?"
    session["conversation_history"].append({"role": "assistant", "content": welcome_msg})

    active_sessions[sid] = session

    return ConversationalResponse(
        session_id=sid,
        message=welcome_msg,
        message_type="general",
        next_action="continue"
    )

@app.post("/answer", response_model=ConversationalResponse)
async def process_answer(req: AnswerRequest):
    """Process user answers with improved flexibility"""
    sess = active_sessions.get(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Update session activity time
    sess["last_activity"] = datetime.now()

    user_answer = req.user_answer.strip()

    # Add user response to conversation history
    sess["conversation_history"].append({"role": "user", "content": user_answer})

    # Check for crisis indicators in any mode
    if detect_crisis(user_answer):
        sess["stage"] = "crisis"

        # Add crisis response to conversation history
        sess["conversation_history"].append({"role": "assistant", "content": CRISIS_RESPONSE})

        return ConversationalResponse(
            session_id=req.session_id,
            message=CRISIS_RESPONSE,
            message_type="urgent",
            next_action="professional_help",
            resources=[
                {
                    "title": "National Suicide Prevention Lifeline",
                    "description": "24/7 support for people in distress",
                    "link": "https://988lifeline.org/"
                },
                {
                    "title": "Crisis Text Line",
                    "description": "Text HOME to 741741 for crisis support",
                    "link": "https://www.crisistextline.org/"
                }
            ]
        )

    # Process based on current stage
    if sess["stage"] == "assessment":
        # Structured assessment flow
        qid = sess["current_question_id"]
        try:
            row = DF_ASSESSMENT[DF_ASSESSMENT.question_id == qid].iloc[0]
            sess["answers"][qid] = user_answer
            next_step = row.next_step

            # Check for exit commands
            if user_answer.lower() in ["stop", "exit", "quit", "change topic", "different topic"]:
                # Switch to conversational mode
                sess["stage"] = "conversation"

                response_msg = get_llm_response(
                    "The user wants to stop the structured assessment. Acknowledge this politely and ask what they'd like to talk about instead.",
                    sess["conversation_history"]
                )

                sess["conversation_history"].append({"role": "assistant", "content": response_msg})

                return ConversationalResponse(
                    session_id=req.session_id,
                    message=response_msg,
                    message_type="general",
                    next_action="continue"
                )

            if next_step == "end_assess":
                # End of assessment, show suggestion
                problem_id = sess["problem_id"]
                sug_df = DF_SUGGESTIONS[DF_SUGGESTIONS.problem_id == problem_id]

                if sug_df.empty:
                    # No suggestions for this problem, use LLM
                    problem_name = DF_PROBLEMS.loc[DF_PROBLEMS.problem_id == problem_id, "problem_name"].iloc[0]

                    # Create an analysis of the user's responses
                    history_text = ""
                    for q_id, ans in sess["answers"].items():
                        q_text = DF_ASSESSMENT.loc[DF_ASSESSMENT.question_id == q_id, "question_text"].iloc[0]
                        history_text += f"Q: {q_text}\nA: {ans}\n\n"

                    suggestion_msg = get_llm_response(
                        f"Based on this assessment about {problem_name}:\n\n{history_text}\n\nProvide a helpful, " +
                        "empathetic response with practical suggestions. Keep it under 200 words.",
                        sess["conversation_history"]
                    )

                    resources = generate_resources(problem_name)

                    # Add response to conversation history
                    sess["conversation_history"].append({"role": "assistant", "content": suggestion_msg})

                    # Transition to feedback stage
                    sess["stage"] = "feedback"
                    sess["feedback_step"] = 0

                    return ConversationalResponse(
                        session_id=req.session_id,
                        message=suggestion_msg,
                        message_type="suggestion",
                        next_action="resources",
                        resources=resources
                    )
                else:
                    # Use predefined suggestion
                    idx = len(sess["suggestions_shown"]) % len(sug_df)
                    srow = sug_df.iloc[idx]
                    sess["suggestions_shown"].append(srow.suggestion_id)

                    # Get first feedback prompt
                    prompt_id = FEEDBACK_SEQUENCE[0]
                    prompt_text = DF_FEEDBACK.loc[DF_FEEDBACK.prompt_id == prompt_id, "prompt_text"].iloc[0]

                    # Format nicely
                    response_msg = f"{srow.suggestion_text}\n\n{prompt_text}"

                    # Add to conversation history
                    sess["conversation_history"].append({"role": "assistant", "content": response_msg})

                    # Transition to feedback stage
                    sess["stage"] = "feedback"
                    sess["feedback_step"] = 0

                    return ConversationalResponse(
                        session_id=req.session_id,
                        message=response_msg,
                        message_type="suggestion",
                        next_action="continue",
                        resources=[{
                            "title": "Learn More",
                            "description": f"Resources for {DF_PROBLEMS.loc[DF_PROBLEMS.problem_id == problem_id, 'problem_name'].iloc[0]}",
                            "link": srow.resource_link
                        }]
                    )

            # Continue to next question in assessment
            try:
                next_row = DF_ASSESSMENT[DF_ASSESSMENT.question_id == next_step].iloc[0]
                sess["current_question_id"] = next_step

                # Add to conversation history
                sess["conversation_history"].append({"role": "assistant", "content": next_row.question_text})

                return ConversationalResponse(
                    session_id=req.session_id,
                    message=next_row.question_text,
                    message_type="question",
                    next_action="continue"
                )
            except IndexError:
                # Question not found, gracefully handle error
                sess["stage"] = "conversation"

                response_msg = get_llm_response(
                    "There was an issue with the assessment. Transition smoothly to a conversational approach and ask how they're feeling now.",
                    sess["conversation_history"]
                )

                # Add to conversation history
                sess["conversation_history"].append({"role": "assistant", "content": response_msg})

                return ConversationalResponse(
                    session_id=req.session_id,
                    message=response_msg,
                    message_type="general",
                    next_action="continue"
                )
        except Exception as e:
            logger.error(f"Error in assessment stage: {e}")
            # Fallback to conversation
            sess["stage"] = "conversation"
            response_msg = "I apologize for the confusion. Let's take a different approach. Could you tell me more about what you're experiencing?"

            # Add to conversation history
            sess["conversation_history"].append({"role": "assistant", "content": response_msg})

            return ConversationalResponse(
                session_id=req.session_id,
                message=response_msg,
                message_type="general",
                next_action="continue"
            )

    # Handle feedback stage
    elif sess["stage"] == "feedback":
        # Check for exit commands
        if user_answer.lower() in ["stop", "exit", "quit", "done", "enough", "no more", "that's enough"]:
            # Build conversation history for summary
            conversation_summary = []
            for msg in sess["conversation_history"]:
                if msg["role"] == "user":
                    conversation_summary.append(f"User: {msg['content']}")
                else:
                    conversation_summary.append(f"Assistant: {msg['content']}")

            conclusion_prompt = f"""
            Based on this conversation, provide a helpful summary and next steps:

            {conversation_summary[-10:]}  # Last 10 messages for context

            Your conclusion should:
            1. Acknowledge what you've learned about their situation
            2. Summarize the key points discussed
            3. Offer 2-3 practical next steps
            4. End on an encouraging note

            Keep it under 200 words and conversational in tone.
            """

            conclusion = get_llm_response(conclusion_prompt, sess["conversation_history"], temperature=0.5)

            sess["stage"] = "conclusion"
            sess["conversation_history"].append({"role": "assistant", "content": conclusion})

            # Generate final resources based on the problem or conversation
            resources = []
            if sess["problem_id"]:
                problem_name = DF_PROBLEMS.loc[DF_PROBLEMS.problem_id == sess["problem_id"], "problem_name"].iloc[0]
                resources = generate_resources(problem_name)
            else:
                # Extract topics from conversation
                topics_prompt = "Based on our conversation, what mental health topics should I provide resources for? List only 1-3 key topics."
                topics_response = get_llm_response(topics_prompt, sess["conversation_history"], temperature=0.3)
                resources = generate_resources(topics_response)

            return ConversationalResponse(
                session_id=req.session_id,
                message=conclusion,
                message_type="conclusion",
                next_action="resources",
                resources=resources
            )

        # Continue with feedback sequence
        step = sess["feedback_step"] + 1

        if step < len(FEEDBACK_SEQUENCE):
            # Get next feedback prompt
            prompt_id = FEEDBACK_SEQUENCE[step]
            prompt_text = DF_FEEDBACK.loc[DF_FEEDBACK.prompt_id == prompt_id, "prompt_text"].iloc[0]

            # Add specific feedback based on user's response
            response_prefix = get_llm_response(
                f"The user responded to your suggestion with: '{user_answer}'. Give a brief (1-2 sentence) acknowledgment.",
                sess["conversation_history"],
                temperature=0.7
            )

            full_response = f"{response_prefix}\n\n{prompt_text}"
            sess["feedback_step"] = step

            # Add to conversation history
            sess["conversation_history"].append({"role": "assistant", "content": full_response})

            return ConversationalResponse(
                session_id=req.session_id,
                message=full_response,
                message_type="general",
                next_action="continue"
            )

        # No more feedback prompts, move to conclusion
        conversation_summary = []
        for msg in sess["conversation_history"]:
            if msg["role"] == "user":
                conversation_summary.append(f"User: {msg['content']}")
            else:
                conversation_summary.append(f"Assistant: {msg['content']}")

        conclusion_prompt = f"""
        Based on this conversation, provide a helpful summary and next steps:

        {conversation_summary[-10:]}  # Last 10 messages for context

        Your conclusion should:
        1. Acknowledge what you've learned about their situation
        2. Summarize the key points discussed
        3. Offer 2-3 practical next steps
        4. End on an encouraging note

        Keep it under 200 words and conversational in tone.
        """

        conclusion = get_llm_response(conclusion_prompt, sess["conversation_history"], temperature=0.5)

        sess["stage"] = "conclusion"
        sess["conversation_history"].append({"role": "assistant", "content": conclusion})

        # Generate final resources
        resources = []
        if sess["problem_id"]:
            problem_name = DF_PROBLEMS.loc[DF_PROBLEMS.problem_id == sess["problem_id"], "problem_name"].iloc[0]
            resources = generate_resources(problem_name)
        else:
            # Extract topics from conversation
            topics_prompt = "Based on our conversation, what mental health topics should I provide resources for? List only 1-3 key topics."
            topics_response = get_llm_response(topics_prompt, sess["conversation_history"], temperature=0.3)
            resources = generate_resources(topics_response)

        return ConversationalResponse(
            session_id=req.session_id,
            message=conclusion,
            message_type="conclusion",
            next_action="resources",
            resources=resources
        )

    # Handle conversational stage
    elif sess["stage"] == "conversation":
        # Analyze user input for potential actions
        analysis = analyze_user_input(user_answer)

        # Check if user wants to switch to a structured assessment
        if "assessment" in user_answer.lower() or "evaluate" in user_answer.lower() or "test" in user_answer.lower():
            # Check if we can identify a problem to assess
            identified_problems = []

            # Check in their current answer
            for topic in analysis["topics"]:
                for idx, problem in enumerate(PROBLEM_LIST):
                    if topic.lower() in problem.lower():
                        pid = DF_PROBLEMS.iloc[idx].problem_id
                        identified_problems.append((pid, problem))
                        break

            # If not found, check in conversation history
            if not identified_problems:
                # Combine recent messages for analysis
                recent_context = " ".join([msg["content"] for msg in sess["conversation_history"][-5:]])
                semantic_matches = semantic_match(recent_context)
                if semantic_matches:
                    identified_problems = [(match["problem_id"], match["problem_name"])
                                         for match in semantic_matches]

            # If we identified a problem, start structured assessment
            if identified_problems:
                pid, problem_name = identified_problems[0]  # Use top match

                # Check if we have assessment questions for this problem
                qs = DF_ASSESSMENT[DF_ASSESSMENT.problem_id == pid]
                if not qs.empty:
                    first = qs.iloc[0]
                    sess["problem_id"] = pid
                    sess["current_question_id"] = first.question_id
                    sess["stage"] = "assessment"

                    response_msg = f"I'd like to learn more about your experience with {problem_name}. {first.question_text}"

                    # Add to conversation history
                    sess["conversation_history"].append({"role": "assistant", "content": response_msg})

                    return ConversationalResponse(
                        session_id=req.session_id,
                        message=response_msg,
                        message_type="question",
                        next_action="continue"
                    )

        # Check if severity warrants resources
        if analysis["severity"] >= 4 or analysis["follow_up_needed"] == "yes":
            # Generate a supportive response with resources
            response_msg = get_llm_response(
                f"The user said: '{user_answer}'. They seem to be dealing with something significant. " +
                "Respond with empathy and validation. Then suggest that you can provide some resources " +
                "that might help. Keep your response under 150 words.",
                sess["conversation_history"]
            )

            # Generate resources based on identified topics
            resources = generate_resources(analysis["topics"][0] if analysis["topics"] else "mental health support")

            # Add response to conversation history
            sess["conversation_history"].append({"role": "assistant", "content": response_msg})

            return ConversationalResponse(
                session_id=req.session_id,
                message=response_msg,
                message_type="general",
                next_action="resources",
                resources=resources
            )

        # Standard conversational response
        response_prompt = f"""
        The user said: '{user_answer}'

        Respond conversationally and with empathy. Consider what they've shared and what might be helpful.
        If appropriate, ask a thoughtful follow-up question. Keep your response under 150 words.

        Don't use generic phrases like "I understand how you feel" unless you genuinely can relate to what they've shared.
        Focus on validation and reflecting back what you've heard while offering gentle guidance when appropriate.
        """

        response_msg = get_llm_response(response_prompt, sess["conversation_history"])

        # Add response to conversation history
        sess["conversation_history"].append({"role": "assistant", "content": response_msg})

        return ConversationalResponse(
            session_id=req.session_id,
            message=response_msg,
            message_type="general",
            next_action="continue"
        )

    # Handle crisis stage
    elif sess["stage"] == "crisis":
        # Check if they're seeking immediate help
        immediate_help_indicators = ["help", "need help", "emergency", "now", "urgent", "immediate"]
        if any(indicator in user_answer.lower() for indicator in immediate_help_indicators):
            response_msg = """
            I strongly encourage you to reach out to one of these resources right now:

            - Call 988 (National Suicide Prevention Lifeline)
            - Text HOME to 741741 (Crisis Text Line)
            - Call 911 or go to your nearest emergency room

            These professionals are trained to help in situations like yours and are available 24/7.
            Would you like me to provide any additional resources?
            """

            # Add to conversation history
            sess["conversation_history"].append({"role": "assistant", "content": response_msg})

            return ConversationalResponse(
                session_id=req.session_id,
                message=response_msg,
                message_type="urgent",
                next_action="professional_help",
                resources=[
                    {
                        "title": "National Suicide Prevention Lifeline",
                        "description": "24/7 support for people in distress",
                        "link": "https://988lifeline.org/"
                    },
                    {
                        "title": "Crisis Text Line",
                        "description": "Text HOME to 741741 for crisis support",
                        "link": "https://www.crisistextline.org/"
                    }
                ]
            )

        # Handle other responses in crisis mode carefully
        response_prompt = f"""
        The user is potentially in crisis and has said: '{user_answer}'

        Respond with extreme care, empathy, and encouragement to seek professional help.
        Validate their feelings, but emphasize the importance of talking to a trained professional.
        Keep your response under 150 words and end with a gentle encouragement to use crisis resources.
        """

        response_msg = get_llm_response(response_prompt, sess["conversation_history"])

        # Add response to conversation history
        sess["conversation_history"].append({"role": "assistant", "content": response_msg})

        return ConversationalResponse(
            session_id=req.session_id,
            message=response_msg,
            message_type="urgent",
            next_action="professional_help",
            resources=[
                {
                    "title": "National Suicide Prevention Lifeline",
                    "description": "24/7 support for people in distress",
                    "link": "https://988lifeline.org/"
                },
                {
                    "title": "Crisis Text Line",
                    "description": "Text HOME to 741741 for crisis support",
                    "link": "https://www.crisistextline.org/"
                }
            ]
        )

    # Handle conclusion stage - restart conversation if user continues
    elif sess["stage"] == "conclusion":
        # Start new conversation thread
        response_msg = get_llm_response(
            f"The user has continued after our conclusion with: '{user_answer}'. " +
            "Acknowledge this and ask how else you can help them today.",
            sess["conversation_history"]
        )

        # Reset session but keep conversation history
        sess["stage"] = "conversation"
        sess["problem_id"] = None
        sess["current_question_id"] = None
        sess["answers"] = {}
        sess["suggestions_shown"] = []
        sess["feedback_step"] = 0

        # Add response to conversation history
        sess["conversation_history"].append({"role": "assistant", "content": response_msg})

        return ConversationalResponse(
            session_id=req.session_id,
            message=response_msg,
            message_type="general",
            next_action="continue"
        )

    # Fallback for unknown states
    fallback_msg = "I'm not sure how to proceed. Let's start fresh. What would you like to talk about today?"

    # Reset session to conversational mode
    sess["stage"] = "conversation"
    sess["conversation_history"].append({"role": "assistant", "content": fallback_msg})

    return ConversationalResponse(
        session_id=req.session_id,
        message=fallback_msg,
        message_type="general",
        next_action="continue"
    )

@app.post("/reset", response_model=ConversationalResponse)
async def reset_session(req: AnswerRequest):
    """Reset an existing session but maintain conversation history"""
    sess = active_sessions.get(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Keep conversation history but reset everything else
    conversation_history = sess["conversation_history"]

    # Create fresh session
    active_sessions[req.session_id] = {
        "problem_id": None,
        "current_question_id": None,
        "answers": {},
        "stage": "conversation",
        "suggestions_shown": [],
        "feedback_step": 0,
        "conversation_history": conversation_history,
        "llm_context": {},
        "created_at": sess["created_at"],  # Maintain original creation time
        "last_activity": datetime.now()
    }

    # Generate response
    reset_response = "Let's start fresh. How can I help you today?"
    active_sessions[req.session_id]["conversation_history"].append({"role": "assistant", "content": reset_response})

    return ConversationalResponse(
        session_id=req.session_id,
        message=reset_response,
        message_type="general",
        next_action="continue"
    )

@app.post("/resources", response_model=List[Dict[str, str]])
async def get_resources(request: Request):
    """Get resources for a specific topic"""
    data = await request.json()
    topic = data.get("topic", "")

    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    return generate_resources(topic)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Middleware to add processing time header and log requests"""
    start_time = datetime.now()
    response = await call_next(request)
    process_time = (datetime.now() - start_time).total_seconds()
    response.headers["X-Process-Time"] = str(process_time)

    # Log request details
    logger.info(f"Path: {request.url.path} | Method: {request.method} | Time: {process_time}s")

    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)