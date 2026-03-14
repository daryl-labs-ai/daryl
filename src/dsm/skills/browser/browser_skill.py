"""
Browser Skill - Web search and navigation skill for DSM-SKILLS.

This skill provides web search and navigation capabilities using Playwright.
It integrates with DSM-SKILLS router for task-based execution.
"""

import os
import sys

# Get to skills directory (parent directory)
skills_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))

# Add skills directory to sys.path
sys.path.insert(0, skills_dir)

# Absolute imports from sibling modules
from models import Skill
from browser_client import BrowserClient


class BrowserSearchSkill(Skill):
    """Web search and navigation skill using Playwright.

    This skill provides web search and navigation capabilities
    using Playwright for browser automation. It allows the DSM-SKILLS
    router to dispatch "search web" tasks to this skill.
    """

    def __init__(self):
        """Initialize browser skill with default properties.

        Creates a BrowserClient instance for executing browser commands.
        """
        # Initialize parent class with skill properties
        super().__init__(
            skill_id="browser_search",
            domain="web",
            description="Perform web search using Playwright",
            trigger_conditions=[
                "search web",
                "find online look up",
                "google search",
                "search the web",
                "web search"
            ]
        )

        # Initialize browser client with headless mode
        self.browser = BrowserClient(headless=True)

    def execute(self, task_description: str) -> str:
        """Execute browser search task.

        Args:
            task_description: The task to execute (e.g., "search web for python asyncio tutorial")

        Returns:
            Extracted search results as string, or error message

        Execution Flow:
        1. Extract search query from task description
        2. Call browser_client.search(query) to perform web search
        3. Return extracted content
        """
        try:
            # Extract search query from task description
            query = self._extract_query(task_description)

            if not query:
                return "Error: No search query found in task description"

            # Build direct search URL (avoid Google blocking headless)
            search_url = f"https://duckduckgo.com/?q={query}"

            # Open search page directly
            result = self.browser.open_page(search_url)

            # Extract visible content from page
            content = self._extract_page_content(result)

            # Close browser after use
            self.browser.close()

            return content

        except Exception as e:
            # Close browser on error
            self.browser.close()
            return f"Error: Browser search failed: {e}"

    def _extract_query(self, task_description: str) -> str:
        """Extract search query from task description.

        Args:
            task_description: The task description (e.g., "search web for python asyncio tutorial")

        Returns:
            Search query string, or empty string if not found
        """
        # Simple keyword-based extraction
        # Look for "search" keyword and extract everything after "for"

        # Try to extract query after "search"
        if "search" in task_description.lower():
            # Split by "search" and take the second part
            parts = task_description.split("search", 1)
            if len(parts) > 1:
                query = parts[1].strip()

                # Remove common prefixes
                query = query.replace("for", "")
                query = query.replace("web", "")
                query = query.replace("online", "")
                query = query.strip()

                # Limit query length
                if len(query) > 100:
                    query = query[:100]

                return query

        # Fallback: use entire description as query
        query = task_description
        query = query.replace("search web for", "")
        query = query.replace("find online look up for", "")
        query = query.replace("google search for", "")
        query = query.strip()

        if len(query) > 100:
            query = query[:100]

        return query

    def _extract_page_content(self, page_info: dict) -> str:
        """Extract and format page content.

        Args:
            page_info: Page info dictionary from open_page

        Returns:
            Formatted string with page content
        """
        formatted = "Browser Search Results:\n"
        formatted += "=" * 60 + "\n\n"

        formatted += f"URL: {page_info.get('url', 'N/A')}\n"
        formatted += f"Title: {page_info.get('title', 'N/A')}\n\n"

        # Extract visible text from content
        content = page_info.get('content', '')

        # Try to find result links
        import re
        links = re.findall(r'href="([^"]+)"', content)
        if links:
            formatted += "Found Links:\n"
            for i, link in enumerate(links[:10], 1):
                formatted += f"  {i}. {link}\n"
        else:
            # Extract first 1000 chars of visible text
            formatted += "Content Preview (first 1000 chars):\n"
            # Strip HTML tags roughly
            text = re.sub(r'<[^>]+>', '', content)
            text = ' '.join(text.split())  # Remove extra whitespace
            formatted += text[:1000]

        formatted += "\n" + "=" * 60

        return formatted
