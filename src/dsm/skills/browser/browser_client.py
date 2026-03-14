"""
Browser Client - Minimal wrapper around Playwright for skill execution.

This module provides a minimal interface for web navigation and content extraction
using Playwright for browser automation.

Playwright capabilities used:
- Navigate to URLs
- Search queries
- Extract text content from selectors
- Get page content (HTML/text)
"""

from playwright.sync_api import sync_playwright, Page, Browser
from typing import List, Optional, Dict, Any


class BrowserClient:
    """Minimal wrapper around Playwright for skill execution.

    This client provides simple methods for navigation, search, and extraction
    using Playwright's headless browser.
    """

    def __init__(self, headless: bool = True):
        """Initialize browser client.

        Args:
            headless: Whether to run browser in headless mode (default True)
        """
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_browser(self) -> None:
        """Ensure browser is started and page is ready."""
        if self._browser is None or self._page is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._page = self._browser.new_page()

    def _close_browser(self) -> None:
        """Close browser and cleanup resources."""
        if self._page:
            self._page.close()
            self._page = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def open_page(self, url: str) -> Dict[str, Any]:
        """Open a specific URL in browser.

        Args:
            url: The URL to open

        Returns:
            Dictionary with page info
        """
        try:
            self._ensure_browser()
            self._page.goto(url, timeout=10000)

            return {
                "url": self._page.url,
                "title": self._page.title(),
                "content": self._page.content()
            }
        except Exception as e:
            raise RuntimeError(f"Failed to open page: {e}")

    def search(self, query: str, engine: str = "google") -> Dict[str, Any]:
        """Search web for a query.

        Args:
            query: Search query string
            engine: Search engine to use (default "google")

        Returns:
            Dictionary with search results
        """
        try:
            self._ensure_browser()

            # Build search URL
            if engine.lower() == "google":
                search_url = f"https://www.google.com/search?q={query}"
            elif engine.lower() == "bing":
                search_url = f"https://www.bing.com/search?q={query}"
            elif engine.lower() == "duckduckgo":
                search_url = f"https://duckduckgo.com/?q={query}"
            else:
                search_url = f"https://www.google.com/search?q={query}"

            # Navigate to search engine
            self._page.goto(search_url, timeout=10000)

            # Wait for page to load
            self._page.wait_for_load_state('networkidle', timeout=5000)

            # Try multiple selectors for search results
            selectors = ['div.g', 'div[data-hveid]', 'div.tF2Cxc', '.search', '.results']
            result_elements = []

            for selector in selectors:
                try:
                    elements = self._page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        result_elements = elements
                        break
                except Exception:
                    continue

            results = []
            for elem in result_elements[:10]:  # Limit to top 10 results
                try:
                    title = elem.query_selector('h3, a')
                    link = elem.query_selector('a')
                    snippet = elem.query_selector('.VwiC3b, .snippet, .description')

                    if title:
                        title_text = title.inner_text()
                    else:
                        title_text = "No title"

                    if link:
                        href = link.get_attribute('href')
                    else:
                        href = ""

                    if snippet:
                        snippet_text = snippet.inner_text()
                    else:
                        snippet_text = ""

                    results.append({
                        "title": title_text,
                        "url": href,
                        "snippet": snippet_text
                    })
                except Exception:
                    continue

            return {
                "query": query,
                "engine": engine,
                "results": results,
                "url": self._page.url,
                "content": self._page.content()
            }

        except Exception as e:
            raise RuntimeError(f"Search failed: {e}")

    def extract_text(self, selector: str) -> Dict[str, Any]:
        """Extract text content from page using CSS selector.

        Args:
            selector: CSS selector to extract text from

        Returns:
            Dictionary with extracted text
        """
        try:
            self._ensure_browser()

            element = self._page.query_selector(selector)
            if element:
                text = element.inner_text()
            else:
                text = ""

            return {
                "selector": selector,
                "text": text
            }
        except Exception as e:
            raise RuntimeError(f"Failed to extract text: {e}")

    def get_page_content(self, url: str) -> str:
        """Get full page content (HTML/text) from a URL.

        Args:
            url: The URL to get content from

        Returns:
            Page content as string
        """
        try:
            self._ensure_browser()
            self._page.goto(url, timeout=10000)
            return self._page.content()
        except Exception as e:
            raise RuntimeError(f"Failed to get page content: {e}")

    def get_current_url(self) -> str:
        """Get current URL from active browser.

        Returns:
            Current URL as string
        """
        try:
            self._ensure_browser()
            return self._page.url
        except Exception as e:
            raise RuntimeError(f"Failed to get current URL: {e}")

    def close_page(self) -> bool:
        """Close current page.

        Returns:
            True if successful
        """
        try:
            if self._page:
                self._page.close()
                self._page = None
            return True
        except Exception:
            return False

    def screenshot_page(self, filename: str) -> bool:
        """Take a screenshot of current page.

        Args:
            filename: Path to save screenshot

        Returns:
            True if successful
        """
        try:
            self._ensure_browser()
            self._page.screenshot(path=filename)
            return True
        except Exception:
            return False

    def execute_javascript(self, code: str) -> str:
        """Execute JavaScript code in active browser.

        Args:
            code: JavaScript code to execute

        Returns:
            Execution result as string
        """
        try:
            self._ensure_browser()
            result = self._page.evaluate(code)
            return str(result)
        except Exception as e:
            raise RuntimeError(f"Failed to execute JavaScript: {e}")

    def wait_for_page_load(self, timeout: int = 10) -> bool:
        """Wait for page to finish loading.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if page loaded successfully
        """
        try:
            self._ensure_browser()
            self._page.wait_for_load_state('networkidle', timeout=timeout * 1000)
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close browser and cleanup all resources."""
        self._close_browser()
