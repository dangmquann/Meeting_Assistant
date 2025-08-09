import openai
from docx import Document
import time
import asyncio
from openai import OpenAI
from openai import APIError
import json

client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key="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",
)

def transcribe_audio(audio_file_path):
    with open(audio_file_path, 'rb') as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file
        )
    return transcription.text



# ---------- Abstract Summary --------------------

def full_abstract_summary_extraction(transcription, meeting_description=None):
    system_prompt = ("You are a highly skilled AI trained in language comprehension and summarization. " +
                     (f"This is a meeting about {meeting_description}. " if meeting_description else "") +
                     f"I would like you to read the following text and summarize it into a concise abstract paragraph. Aim to retain the most important points, providing a coherent and readable summary that could help a person understand the main points of the discussion without needing to read the entire text. Please avoid unnecessary details or tangential points.")

    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": transcription
            }
        ]
    )
    return response.choices[0].message.content

def chunked_abstract_summary_extraction(transcription, meeting_description=None):
    max_tokens = 8000  # A bit less than 8192 to leave some room for the system message
    overlap = 1000  # Overlap size - tune this based on your use case

    transcript_parts = [transcription[i:i + max_tokens + overlap] for i in range(0, len(transcription), max_tokens)]

    final_summary = ""
    previous_summary = ""  # Initialize previous summary

    for part in transcript_parts:
        # Generate a summary of the chunk
        system_prompt = ("You are a highly skilled AI trained in language comprehension and summarization. " +
                         (f"This is a meeting about {meeting_description}. " if meeting_description else "") +
                         f"Previously, you summarized: '{previous_summary}'. Now, I would like you to read the following text and summarize it into a concise abstract paragraph, building upon your previous summary. Aim to retain the most important points, providing a coherent and readable summary that could help a person understand the main points of the discussion without needing to read the entire text. Please avoid unnecessary details or tangential points.")

        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": part
                }
            ]
        )

        previous_summary = response.choices[0].message.content  # Update previous summary
        final_summary += previous_summary + "\n"

    # Use GPT-4 to rephrase the final summary into a more cohesive paragraph
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "As an AI trained in language comprehension and summarization, your task is to rephrase the following summaries into a more cohesive and concise paragraph. Please maintain the overall meaning and key details in your rephrasing."
            },
            {
                "role": "user",
                "content": final_summary
            }
        ]
    )

    final_summary = response.choices[0].message.content

    return final_summary

def abstract_summary_extraction(transcription, meeting_description=None):
    try:
        # Try the original method first
        return full_abstract_summary_extraction(transcription, meeting_description)
    except Exception as e:
        # If the original method fails due to exceeding the maximum token limit, fall back to the chunking method
        if 'token' in str(e):
            print("Using chunking for abstract summary extraction.")
            # If the server returns a 502, wait 10 seconds then retry
            try:
                return chunked_abstract_summary_extraction(transcription, meeting_description)
            except APIError as e:
                if e.http_status == 502:
                    print("API returned a 502 Bad Gateway error. Retrying in 10 seconds...")
                    time.sleep(10)
                    return chunked_abstract_summary_extraction(transcription, meeting_description)
                else:
                    # If the error is due to another reason, raise it
                    raise e
        else:
            # If the error is due to another reason, raise it
            raise e


# ---------- Key Points --------------------

def full_key_points_extraction(transcription, meeting_description = None):
    system_prompt = ("You are a proficient AI with a specialty in distilling informartion into key points. " +
                     (f"This is a meeting about {meeting_description}. " if meeting_description else "") +
                     f"Based on the following text, identify and list the main points that were discussed or brought up. These should be the most important ideas, findings, or topics that are crucial to the essence of the discussion. Your goal is to provide a list that someone could read to quickly understand what was talked about.")

    response = client.chat.completions.create(
        model = "gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": transcription
            }
        ]
    )
    return response.choices[0].message.content

def chunked_key_points_extraction(transcription, meeting_description = None):
    max_tokens = 8000 # A bit less than 8192 to leave some room for the system message
    overlap = 1000 # Overlap size - tune this based on your use case

    transcipt_parts = [transcription[i : i + max_tokens + overlap] for i in range(0, len(transcription), max_tokens)]

    final_key_points = []
    previous_key_points = ""  # Initialize previous key points

    for part in transcipt_parts:
        # Extract key points from the chunk
        system_prompt = ("You are a proficient AI with a specialty in distilling information into key points. " +
                         (f"This is a meeting about {meeting_description}. " if meeting_description else "") +
                         f"Previously, you identified: '{previous_key_points}'. Now, based on the following text, identify and list the main points that were dicussed or brought up. These should be the most important ideas, findings, or topics that are crucial to the essence of the discussion. Your goal is to provide a list that someone could read to quickly understand what was talked about.")

        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": part
                }
            ]
        )

        previous_key_points = response.choices[0].message.content  # Update previous key points
        final_key_points.append(previous_key_points)
    
    # Combine all key points into a single list
    all_key_points = "\n".join(final_key_points)

    # Use GPT-4 to reformat and renumber the key points
    system_prompt = (
        "You are a proficient AI with a specialty in organizing and formatting information. " + 
        f"Please take the following key points{f' (from a meeting about {meeting_description})' if meeting_description else ''} and reformat them into a coherent, numbered list. Ensure that the numbering is consistent, starts at number 1, and does not restart. Each key points should start on a new line."
    )

    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": all_key_points
            }

        ]
    )

    final_key_points = response.choices[0].message.content
    return final_key_points


def key_points_extraction(transcription, meeting_description=None):
    try:
        # Try the original method first
        return full_key_points_extraction(transcription, meeting_description)
    except Exception as e:
        # If the original method fails due to exceeding the maximum token limit, fall back to the chunking method
        if 'token' in str(e):
            print("Using chunking for key points extraction.")
            # If the server returns a 502, wait 10 seconds then retry
            try:
                return chunked_key_points_extraction(transcription, meeting_description)
            except APIError as e:
                if e.http_status == 502:
                    print("API returned a 502 Bad Gateway error. Retrying in 10 seconds...")
                    time.sleep(10)
                    return chunked_key_points_extraction(transcription, meeting_description)
                else:
                    # If the error is due to another reason, raise it
                    raise e
        else:
            # If the error is due to another reason, raise it
            raise e


# ---------- Action Items --------------------

def full_action_item_extraction(transcription, meeting_description=None):
    system_prompt = ("You are an AI expert in analyzing conversations and extracting action items. " +
                     (f"This is a meeting about {meeting_description}. " if meeting_description else "") +
                     f"Please review the text and identify any tasks, assignments, or actions that were agreed upon or mentioned as needing to be done. These could be tasks assigned to specific individuals, or general actions that the group has decided to take. Please list these action items clearly and concisely.")

    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": transcription
            }
        ]
    )
    return response.choices[0].message.content


def chunked_action_item_extraction(transcription, meeting_description=None):
    max_tokens = 8000  # A bit less than 8192 to leave some room for the system message
    overlap = 1000  # Overlap size - tune this based on your use case

    transcript_parts = [transcription[i:i + max_tokens + overlap] for i in range(0, len(transcription), max_tokens)]

    final_action_items = ""
    previous_action_items = ""  # Initialize previous action items

    for part in transcript_parts:
        # Extract action items from the chunk
        system_prompt = ("You are an AI expert in analyzing conversations and extracting action items. " +
                         (f"This is a meeting about {meeting_description}. " if meeting_description else "") +
                         f"Previously, you identified: '{previous_action_items}'. Now, please review the text and identify any tasks, assignments, or actions that were agreed upon or mentioned as needing to be done, building upon your previous list. These could be tasks assigned to specific individuals, or general actions that the group has decided to take. Please list these action items clearly and concisely.")

        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": part
                }
            ]
        )

        previous_action_items = response.choices[0].message.content  # Update previous action items
        final_action_items += previous_action_items + "\n"

    # Use GPT-4 to consolidate the action items into a single, coherent list
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "As an AI with expertise in synthesizing information, your task is to consolidate the following action items into a single, concise, and coherent list. Ensure the list is organized in a clear and concise manner. Do not overwhelm the reader with too many action items."
            },
            {
                "role": "user",
                "content": final_action_items
            }
        ]
    )

    final_action_items = response.choices[0].message.content

    return final_action_items


def action_item_extraction(transcription, meeting_description=None):
    try:
        # Try the original method first
        return full_action_item_extraction(transcription, meeting_description)
    except Exception as e:
        # If the original method fails due to exceeding the maximum token limit, fall back to the chunking method
        if 'token' in str(e):
            print("Using chunking for action item extraction.")
            # If the server returns a 502, wait 10 seconds then retry
            try:
                return chunked_action_item_extraction(transcription, meeting_description)
            except APIError as e:
                if e.http_status == 502:
                    print("API returned a 502 Bad Gateway error. Retrying in 10 seconds...")
                    time.sleep(10)
                    return chunked_action_item_extraction(transcription, meeting_description)
                else:
                    # If the error is due to another reason, raise it
                    raise e
        else:
            # If the error is due to another reason, raise it
            raise e


# ---------- Sentiment Analysis --------------------

def full_sentiment_analysis(transcription, meeting_description=None):
    system_prompt = ("As an AI with expertise in language and emotion analysis, your task is to analyze the sentiment of the following text. " +
                     (f"This is a meeting about {meeting_description}. " if meeting_description else "") +
                     f"Please consider the overall tone of the discussion, the emotion conveyed by the language used, and the context in which words and phrases are used. Indicate whether the sentiment is generally positive, negative, or neutral, and provide brief explanations for your analysis where possible.")

    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": transcription
            }
        ]
    )
    return response.choices[0].message.content


def chunked_sentiment_analysis(transcription, meeting_description=None):
    max_tokens = 8000  # A bit less than 8192 to leave some room for the system message
    overlap = 1000  # Overlap size - tune this based on your use case

    transcript_parts = [transcription[i:i + max_tokens + overlap] for i in range(0, len(transcription), max_tokens)]

    final_sentiment = ""
    previous_sentiment = ""  # Initialize previous sentiment

    for part in transcript_parts:
        # Analyze the sentiment of the chunk
        system_prompt = (
                    "As an AI with expertise in language and emotion analysis, your task is to analyze the sentiment of the following text. " +
                    (f"This is a meeting about {meeting_description}. " if meeting_description else "") +
                    f"Previously, you analyzed: '{previous_sentiment}'. Now, please consider the overall tone of the discussion, the emotion conveyed by the language used, and the context in which words and phrases are used. Indicate whether the sentiment is generally positive, negative, or neutral, and provide brief explanations for your analysis where possible.")

        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": part
                }
            ]
        )

        previous_sentiment = response.choices[0].message.content  # Update previous sentiment
        final_sentiment += previous_sentiment + "\n"

    # Use GPT-4 to rephrase the final sentiment analysis into a more cohesive paragraph
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "As an AI with expertise in language and emotion analysis, your task is to rephrase the following sentiment analysis into a more cohesive and concise paragraph. Please maintain the overall sentiment and key details in your rephrasing."
            },
            {
                "role": "user",
                "content": final_sentiment
            }
        ]
    )

    final_sentiment = response.choices[0].message.content

    return final_sentiment


def sentiment_analysis(transcription, meeting_description=None):
    try:
        # Try the original method first
        return full_sentiment_analysis(transcription, meeting_description)
    except Exception as e:
        # If the original method fails due to exceeding the maximum token limit, fall back to the chunking method
        if 'token' in str(e):
            print("Using chunking for sentiment analysis.")
            # If the server returns a 502, wait 10 seconds then retry
            try:
                return chunked_sentiment_analysis(transcription, meeting_description)
            except APIError as e:
                if e.http_status == 502:
                    print("API returned a 502 Bad Gateway error. Retrying in 10 seconds...")
                    time.sleep(10)
                    return chunked_sentiment_analysis(transcription, meeting_description)
                else:
                    # If the error is due to another reason, raise it
                    raise e
        else:
            # If the error is due to another reason, raise it
            raise e
        

def extract_chapters(transcription, meeting_description=None):
    """
    Segment a transcript into chapters based on topic transitions.
    Returns chapters with timestamps, titles, and key points.
    """
    system_prompt = f"""You are an expert at identifying major topic transitions in meeting transcripts.
    {f'This is a meeting about {meeting_description}.' if meeting_description else ''}
    
    Analyze the following transcript and:
    1. Identify 3-7 major topic transitions where the conversation significantly shifts focus
    2. Create informative chapter titles that are specific but broad enough to cover related points
    3. Note the approximate timestamp where each topic begins (assume the meeting starts at 00:00)
    4. For each chapter, provide 2-3 concise key points that capture the most crucial information
    
    Format your response as JSON:
    {{
        "chapters": [
            {{
                "timestamp": "MM:SS",
                "title": "Chapter Title",
                "key_points": ["Point 1", "Point 2", "Point 3"]
            }},
            ...
        ]
    }}
    
    Do not create chapters for brief mentions or subtopics. Focus on major transitions only.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": transcription
                }
            ]
        )
        
        return json.loads(response.choices[0].message.content)
    
    except Exception as e:
        print(f"Error extracting chapters: {str(e)}")
        # If the transcript is too long, implement a chunking approach
        if 'token' in str(e):
            print("Transcript too long, implementing chunking for chapter extraction")
            return chunked_extract_chapters(transcription, meeting_description)
        else:
            raise e

def chunked_extract_chapters(transcription, meeting_description=None):
    """Handle long transcripts by chunking them and then merging chapter results"""
    max_tokens = 8000
    overlap = 1000
    
    # Split transcript into chunks with overlap
    chunks = [transcription[i:i+max_tokens] for i in range(0, len(transcription), max_tokens-overlap)]
    
    all_chapters = []
    estimated_words_per_minute = 150
    
    for i, chunk in enumerate(chunks):
        # Estimate timestamp for the beginning of this chunk
        chunk_start_time = i * (max_tokens-overlap) / 5 / estimated_words_per_minute  # rough estimate in minutes
        
        system_prompt = f"""You are analyzing part {i+1} of a longer transcript.
        {f'This is a meeting about {meeting_description}.' if meeting_description else ''}
        
        Identify any major topic transitions in this section of the transcript.
        The approximate start time for this section is around {int(chunk_start_time)} minutes into the meeting.
        
        Create informative chapter titles and 2-3 key points for each topic transition.
        
        Format your response as JSON:
        {{
            "chapters": [
                {{
                    "timestamp": "MM:SS", 
                    "title": "Chapter Title",
                    "key_points": ["Point 1", "Point 2"]
                }}
            ]
        }}
        
        Only identify significant topic transitions. If this chunk doesn't contain any clear topic transitions, return an empty chapters array.
        """
        
        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": chunk}
            ]
        )
        
        chunk_chapters = json.loads(response.choices[0].message.content).get("chapters", [])
        all_chapters.extend(chunk_chapters)
    
    # If we have too many chapters, merge similar ones
    if len(all_chapters) > 7:
        all_chapters_json = json.dumps(all_chapters)
        
        consolidation_prompt = f"""These chapter markers were extracted from a long transcript but there are too many.
        Please consolidate them into 5-7 major chapters by merging similar topics.
        Keep the earliest timestamp when merging chapters and combine key points.
        
        Original chapters: {all_chapters_json}
        
        Return the consolidated chapters in the same JSON format:
        {{
            "chapters": [
                {{
                    "timestamp": "MM:SS", 
                    "title": "Chapter Title",
                    "key_points": ["Point 1", "Point 2", "Point 3"]
                }}
            ]
        }}
        """
        
        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0.2,
            messages=[
                {"role": "system", "content": consolidation_prompt}
            ]
        )
        
        return json.loads(response.choices[0].message.content)
    
    return {"chapters": all_chapters}


# ---------- Main Functions --------------------

def save_as_docx(minutes, filename):
    doc = Document()
    
    # Process standard sections first
    for key, value in minutes.items():
        if key != 'chapters':  # Handle chapters separately
            # Replace underscores with spaces and capitalize each word for the heading
            heading = ' '.join(word.capitalize() for word in key.split('_'))
            doc.add_heading(heading, level=1)
            doc.add_paragraph(value)
            # Add a line break between sections
            doc.add_paragraph()
    
    # Add chapters section if available
    if 'chapters' in minutes:
        doc.add_heading('Meeting Chapters', level=1)
        
        for chapter in minutes['chapters']:
            # Add chapter with timestamp
            chapter_title = f"[{chapter['timestamp']}] {chapter['title']}"
            doc.add_heading(chapter_title, level=2)
            
            # Add key points as a bullet list
            for point in chapter['key_points']:
                doc.add_paragraph(point, style='List Bullet')
            
        # Add a line break after chapters
        doc.add_paragraph()
    
    doc.save(filename)


def meeting_minutes(transcription, meeting_description=None):
    abstract_summary = abstract_summary_extraction(transcription, meeting_description)
    key_points = key_points_extraction(transcription, meeting_description)
    action_items = action_item_extraction(transcription, meeting_description)
    sentiment = sentiment_analysis(transcription, meeting_description)
    chapters = extract_chapters(transcription, meeting_description)
    return {
        'abstract_summary': abstract_summary,
        'key_points': key_points,
        'action_items': action_items,
        'sentiment': sentiment,
        'chapters': chapters['chapters']  # Store just the chapters array
    }


if __name__ == '__main__':
    audio_file_path = "/home/quandm/quandm/agent-be/EarningsCall.mp3"

    # Ask the user for an optional meeting description
    meeting_description = input('Complete the sentence: "This is a meeting about..." (or press Enter to skip): ')
    # If the user didn't provide a description, set meeting_description to None
    if meeting_description.strip() == "":
        meeting_description = None

    # transcription = transcribe_audio(audio_file_path)
    txt_file_path = "/home/quandm/quandm/agent-be/V2_chat/controller/speech/meeting/transcript.txt"
    with open(txt_file_path, "r", encoding="utf-8") as f:
        transcription = f.read()
    print(transcription)  # TODO: not necessary

    minutes = meeting_minutes(transcription, meeting_description)
    print(minutes)

    save_as_docx(minutes, './meeting_minutes_phone.docx')