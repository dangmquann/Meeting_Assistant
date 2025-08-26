import os
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from .helper_functions import (
    EmbeddingProvider,
    retrieve_context_per_question,
    replace_t_with_space,
    get_langchain_embedding_provider,
    show_context
)
from dotenv import load_dotenv

load_dotenv()

def encode_pdf(pathm, chunk_size=1000, chunk_overlap=200):
    """
    Encode pdf book into a vector store using OpenAI embeddings.

    Args:
        pathm (str): Path to the PDF file.
        chunk_size (int): Size of each text chunk.
        chunk_overlap (int): Overlap between chunks.
    Returns:
        A FAISS vector store containing the text chunks from the PDF.
    """
    loader = PyPDFLoader(pathm)
    documents = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap
    )

    text = text_splitter.split_documents(documents)
    cleaned_texts = replace_t_with_space(text)

    # Create embeddings 
    embeddings = get_langchain_embedding_provider(EmbeddingProvider.OPENAI)

    # Create vector store
    vectorstore = FAISS.from_documents(
        cleaned_texts,
        embeddings
    )

    return vectorstore




if __name__ == "__main__":
    # Example usage
    pdf_path = "modules/speech/meeting/llm_rag/data/Understanding_Climate_Change.pdf"
    chunks_vector_store = encode_pdf(pdf_path)

    # Create retriever
    chunks_query_retriever = chunks_vector_store.as_retriever(
        search_kwargs={"k": 2}
    )
    
    # Show context for a sample question
    question = "What is the main cause of climate change?"
    context = retrieve_context_per_question(question, chunks_query_retriever)
    show_context(context)
    
    print("Vector store created and context retrieved successfully.")