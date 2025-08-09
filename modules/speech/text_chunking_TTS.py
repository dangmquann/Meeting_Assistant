import re

MIN_BUFFER_THRESHOLD = 50   # Độ dài tối thiểu của một chunk
MAX_BUFFER_THRESHOLD = 150  # Độ dài tối đa của một chunk
SENTENCE_ENDINGS = (".", "?", "!", ":", ";", ",", "\n")  # Các ký tự kết thúc câu
CLAUSE_BOUNDARIES = r'\.|\?|!|;|, (and|but|or|nor|for|yet|so)'

# Chunking + Streaming TTS
def chunk_text_by_sentence(text, min_length=MIN_BUFFER_THRESHOLD, max_length=MAX_BUFFER_THRESHOLD):
    """
    Chia nhỏ text thành các chunk theo ranh giới câu, đảm bảo mỗi chunk có độ dài hợp lý.
    - min_length: độ dài tối thiểu của một chunk (nếu câu quá ngắn sẽ nối với câu tiếp theo)
    - max_length: độ dài tối đa của một chunk (nếu câu quá dài sẽ cắt nhỏ hơn)
    """
    # Tìm ranh giới câu bằng regex
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    buffer = ""

    for sentence in sentences:
        if not sentence.strip():
            continue
        # Gom buffer nếu câu quá ngắn
        if len(buffer) + len(sentence) < min_length:
            buffer += " " + sentence if buffer else sentence
            continue
        # Nếu buffer đủ dài, thêm vào chunk
        if buffer:
            chunks.append(buffer.strip())
            buffer = ""
        # Nếu câu quá dài, cắt nhỏ hơn
        while len(sentence) > max_length:
            chunks.append(sentence[:max_length].strip())
            sentence = sentence[max_length:]
        buffer = sentence

    if buffer:
        chunks.append(buffer.strip())
    return chunks


# Chunk by Maximum Number of Characters.
def chunk_text(text, chunk_size):
    chunks = []
    words = text.split()
    current_chunk = ''
    for word in words:
        if len(current_chunk) + len(word) <= chunk_size:
            current_chunk += ' ' + word
        else:
            chunks.append(current_chunk.strip())
            current_chunk = word
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

# Chunk by Clause and setences Boundaries
def chunk_text_by_clause(text):
    # Find clause boundaries using regular expression
    clause_boundaries = re.finditer(CLAUSE_BOUNDARIES, text)
    boundaries_indices = [boundary.start() for boundary in clause_boundaries]
    chunks = []
    start = 0
    for boundary_index in boundaries_indices:
        chunks.append(text[start:boundary_index + 1].strip())
        start = boundary_index + 1
    # Append the remaining part of the text
    chunks.append(text[start:].strip())
    return chunks

# Dynamic Chunking
def chunk_text_dynamically(text):
    # Find clause boundaries using regular expression
    clause_boundaries = re.finditer(CLAUSE_BOUNDARIES, text)
    boundaries_indices = [boundary.start() for boundary in clause_boundaries]
    chunks = []
    start = 0
    # Add chunks until the last clause boundary
    for boundary_index in boundaries_indices:
        chunk = text[start:boundary_index + 1].strip()
        if len(chunk) <= MAX_BUFFER_THRESHOLD:
            chunks.append(chunk)
        else:
            # Split by comma if it doesn't create subchunks less than three words
            subchunks = chunk.split(',')
            temp_chunk = ''
            for subchunk in subchunks:
                if len(temp_chunk) + len(subchunk) <= MAX_BUFFER_THRESHOLD:
                    temp_chunk += subchunk + ','
                else:
                    if len(temp_chunk.split()) >= 3:
                        chunks.append(temp_chunk.strip())
                    temp_chunk = subchunk + ','
            if temp_chunk:
                if len(temp_chunk.split()) >= 3:
                    chunks.append(temp_chunk.strip())
        start = boundary_index + 1
    # Split remaining text into subchunks if needed
    remaining_text = text[start:].strip()
    if remaining_text:
        remaining_subchunks = [remaining_text[i:i+MAX_BUFFER_THRESHOLD] for i in range(0, len(remaining_text), MAX_BUFFER_THRESHOLD)]
        chunks.extend(remaining_subchunks)
    return chunks