# bot/knowledge_base.py
import logging
import os
from typing import List

from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader

log = logging.getLogger(__name__)

class KnowledgeBase:
    """
    Manages the creation, loading, and querying of a vector-based knowledge base
    using a Retrieval-Augmented Generation (RAG) approach with FAISS.
    """
    def __init__(self, index_path: str = "kb_index.faiss", api_key: str = None):
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is required for KnowledgeBase embeddings.")

        self.index_path = index_path
        self.embeddings = OpenAIEmbeddings(openai_api_key=api_key)
        self.vector_store = None

        if self.exists():
            self.load_local()
        else:
            log.info("No existing knowledge base found. Please build one from files.")

    def load_local(self):
        """Loads a pre-existing FAISS index from the local disk."""
        log.info(f"Loading existing knowledge base from {self.index_path}...")
        try:
            # allow_dangerous_deserialization is required for FAISS with langchain
            self.vector_store = FAISS.load_local(
                self.index_path,
                self.embeddings,
                allow_dangerous_deserialization=True
            )
            log.info("Knowledge base loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load knowledge base from '{self.index_path}': {e}", exc_info=True)
            self.vector_store = None

    def build_from_files(self, file_paths: List[str]):
        """
        Builds a new knowledge base from a list of text file paths.
        This involves loading, chunking, embedding, and saving the documents.
        """
        log.info(f"Building knowledge base from {len(file_paths)} files...")
        docs = []
        for file_path in file_paths:
            try:
                loader = TextLoader(file_path, encoding='utf-8')
                docs.extend(loader.load())
            except Exception as e:
                log.error(f"Error loading file {file_path}: {e}")
                continue

        if not docs:
            log.warning("No documents were loaded. Knowledge base not built.")
            return

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_documents(docs)
        log.info(f"Loaded {len(docs)} documents, split into {len(chunks)} chunks.")

        try:
            log.info("Creating vector store and embeddings... (This may take a moment)")
            self.vector_store = FAISS.from_documents(chunks, self.embeddings)
            self.vector_store.save_local(self.index_path)
            log.info(f"Knowledge base built and saved to {self.index_path}")
        except Exception as e:
            log.error(f"Failed to create and save vector store: {e}", exc_info=True)
            raise

    def query(self, text: str, k: int = 3) -> str:
        """
        Queries the knowledge base to find the most relevant context for a given text.
        """
        if not self.vector_store:
            log.warning("Cannot query: Knowledge base is not available.")
            return ""

        log.debug(f"Querying knowledge base with k={k} for: '{text[:50]}...'")
        try:
            relevant_docs = self.vector_store.similarity_search(text, k=k)
            if not relevant_docs:
                return ""

            context = "\n\n---\n\n".join([doc.page_content for doc in relevant_docs])
            log.debug(f"Retrieved context of {len(context)} chars.")
            return context
        except Exception as e:
            log.error(f"Error during knowledge base query: {e}", exc_info=True)
            return ""

    def clear(self):
        """Deletes the knowledge base index files from disk."""
        log.info(f"Clearing knowledge base. Deleting index at '{self.index_path}'...")
        # FAISS creates two files: index.faiss and index.pkl
        if os.path.exists(self.index_path):
            os.remove(self.index_path)

        pkl_path = f"{self.index_path}.pkl"
        if os.path.exists(pkl_path):
            os.remove(pkl_path)

        self.vector_store = None
        log.info("Knowledge base cleared.")

    def exists(self) -> bool:
        """Checks if the knowledge base index file exists on disk."""
        return os.path.exists(self.index_path)
