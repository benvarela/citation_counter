import pickle
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Configure logging to show on console
logging.basicConfig(level=logging.INFO, format='[%(name)s][%(levelname)s]: %(message)s')
logger_tmp = logging.getLogger('elsapy.utils')
logger_tmp.propagate = False
logger_tmp = logging.getLogger('elsapy.elsclient')
logger_tmp.propagate = False
logger_tmp = logging.getLogger('httpx')
logger_tmp.propagate = False  # Remove this if you want to diagnose why SemanticScholar is not working

class ResultsCache:
    """
    A caching system for storing search results by DOI.
    
    Attributes
    ----------
    db_name : str
        Name of the database (e.g., 'elsevier', 'semanticscholar', 'openalex')
    cache : Dict[str, Any]
        Dictionary mapping DOI to stored objects
    cache_file : Path
        Path to the pickle file for persistent storage
    cache_disabled : bool
        If True, all cache operations are bypassed
    """
    
    def __init__(self, db_name: str, cache_disabled: bool = False):
        """
        Initialize the ResultsCache.
        
        Parameters
        ----------
        db_name : str
            Name of the database (e.g., 'elsevier')
        cache_disabled : bool, optional
            If True, disable all caching operations (default: False)
        """
        self._logger = logging.getLogger(f"Cache-{db_name}")
        self.db_name = db_name
        self.cache_disabled = cache_disabled
        self.cache: Dict[str, Any] = {}
        
        if not self.cache_disabled:
            # Create cache directory if it doesn't exist
            cache_dir = Path("data/cache")
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            self.cache_file = cache_dir / f"{db_name}.pkl"
            self._load_cache()
        else:
            self._logger.info(f"Cache disabled for {db_name}")
            self.cache_file = None
    
    def _load_cache(self) -> None:
        """Load cache from pickle file if it exists."""
        self._logger.info(f"Checking for an existing cache at {self.cache_file}")
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    self.cache = pickle.load(f)
                num_cache = str(len(self.cache))
                self._logger.info(f"Loaded {num_cache} values from the {self.db_name} cache on disk.")
            except (pickle.PickleError, EOFError, FileNotFoundError):
                self.cache = {}
                self._logger.error(f"Could not load the cache for {self.db_name} from {self.cache_file}."
                                   f" Starting a new cache...")
        else:
            self._logger.info(f"No existing cache found for {self.db_name}. Starting a new cache...")
    
    def _save_cache(self, force_save = False) -> None:
        """
        Save cache to pickle file. By default, it will do this every 25th entry

        Parameters
        ----------
        force_save : bool
            Whether to force saving the cache irrespective of number of entries
        """
        if self.cache_disabled:
            return
            
        if self.size() % 25 != 0 and not force_save:
            return
        
        temp_file = self.cache_file.with_suffix('.tmp')
        try:
            # Write to temporary file first
            with open(temp_file, 'wb') as f:
                pickle.dump(self.cache, f)
            
            # Atomically replace the old file with the new one
            if self.cache_file.exists():
                os.remove(self.cache_file)
            os.rename(temp_file, self.cache_file)
            
        except Exception as e:
            # Clean up temp file if it exists
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except:
                    pass
            print(f"Warning: Could not save cache to {self.cache_file}: {e}")

    def save_to_disk(self):
        """Ensures the latest copy of the cache is saved to disk."""
        if not self.cache_disabled:
            self._save_cache(force_save=True)
    
    def get(self, doi: str) -> Optional[Any]:
        """
        Get cached result for a DOI.
        
        Parameters
        ----------
        doi : str
            The DOI to look up
            
        Returns
        -------
        Any or None
            The cached object if found, None otherwise
        """
        if self.cache_disabled:
            return None
        return self.cache.get(doi)
    
    def set(self, doi: str, result: Any) -> None:
        """
        Store a result in the cache.
        
        Parameters
        ----------
        doi : str
            The DOI key
        result : Any
            The object to cache
        """
        if self.cache_disabled:
            return
        self.cache[doi] = result
        self._save_cache()
    
    def has(self, doi: str) -> bool:
        """
        Check if DOI exists in cache.
        
        Parameters
        ----------
        doi : str
            The DOI to check
            
        Returns
        -------
        bool
            True if DOI exists in cache, False otherwise
        """
        if self.cache_disabled:
            return False
        return doi in self.cache
    
    def clear(self) -> None:
        """Clear all cached results."""
        if self.cache_disabled:
            return
        self.cache.clear()
        self._save_cache()
    
    def size(self) -> int:
        """Return the number of cached items."""
        if self.cache_disabled:
            return 0
        return len(self.cache)