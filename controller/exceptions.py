class ArxivAPIException(Exception):
    """Base exception for Arxiv API errors."""

class ArxivAPITimeoutError(ArxivAPIException):
    """Exception for Arxiv API timeouts."""

class ArxivAPIRateLimitError(ArxivAPIException):
    """Exception for Arxiv API rate limiting."""

class ArxivParseError(ArxivAPIException):
    """Exception for errors parsing Arxiv API responses."""


class ParsingException(Exception):
    """Base exception for parsing-related errors."""
class PDFParsingException(ParsingException):
    """Base exception for PDF parsing-related errors."""

class PDFDownloadException(Exception):
    """Base exception for PDF download errors."""

class PDFDownloadTimeoutError(PDFDownloadException):
    """Exception for PDF download timeouts."""

class PDFDownloadError(PDFDownloadException):
    """Exception for errors during PDF download."""