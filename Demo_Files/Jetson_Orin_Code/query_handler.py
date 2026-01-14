#!/usr/bin/env python3
"""
Sentinel Nexus V2 - Query Handler
Manages AI query processing and result generation.
"""

import time
import logging
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from queue import Queue, Empty
import json

logger = logging.getLogger(__name__)

@dataclass
class QueryRequest:
    """Represents a query request"""
    query_id: str
    query_text: str
    client_id: str
    timestamp: float
    priority: int = 0

@dataclass
class QueryResult:
    """Represents a query result"""
    query_id: str
    response: str
    confidence: float
    processing_time: float
    frame_count: int
    timestamp: float
    image_data: Optional[bytes] = None

class QueryHandler:
    """Handles AI query processing and result generation"""
    
    def __init__(self, max_queue_size: int = 10):
        self.max_queue_size = max_queue_size
        self.query_queue = Queue(maxsize=max_queue_size)
        self.processing = False
        self.stats = {
            'total_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'average_processing_time': 0.0
        }
        
    def add_query(self, query_request: QueryRequest) -> bool:
        """Add a query to the processing queue"""
        try:
            if self.query_queue.full():
                logger.warning("Query queue is full, dropping oldest query")
                try:
                    self.query_queue.get_nowait()
                except Empty:
                    pass
            
            self.query_queue.put(query_request)
            logger.info(f"Added query to queue: {query_request.query_text[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error adding query to queue: {e}")
            return False
    
    def process_queries(self, vila_processor):
        """Process queries from the queue"""
        self.processing = True
        logger.info("Query processing started")
        
        while self.processing:
            try:
                # Get next query from queue
                query_request = self.query_queue.get(timeout=1.0)
                
                # Process the query
                result = self._process_single_query(query_request, vila_processor)
                
                if result:
                    self._update_stats(result)
                    logger.info(f"Query processed successfully: {query_request.query_text[:50]}...")
                else:
                    logger.error(f"Failed to process query: {query_request.query_text[:50]}...")
                    self.stats['failed_queries'] += 1
                
                self.stats['total_queries'] += 1
                
            except Empty:
                # No queries in queue, continue
                continue
            except Exception as e:
                logger.error(f"Error processing query: {e}")
                self.stats['failed_queries'] += 1
                self.stats['total_queries'] += 1
    
    def _process_single_query(self, query_request: QueryRequest, vila_processor) -> Optional[QueryResult]:
        """Process a single query"""
        try:
            start_time = time.time()
            
            # Process with VILA
            if vila_processor:
                result = vila_processor.process_query(query_request.query_text)
                
                processing_time = time.time() - start_time
                
                return QueryResult(
                    query_id=query_request.query_id,
                    response=result.get('response', ''),
                    confidence=result.get('confidence', 0.0),
                    processing_time=processing_time,
                    frame_count=result.get('frame_count', 0),
                    timestamp=time.time(),
                    image_data=result.get('image_data')
                )
            else:
                logger.error("VILA processor not available")
                return None
                
        except Exception as e:
            logger.error(f"Error processing single query: {e}")
            return None
    
    def _update_stats(self, result: QueryResult):
        """Update processing statistics"""
        self.stats['successful_queries'] += 1
        
        # Update average processing time
        total_successful = self.stats['successful_queries']
        current_avg = self.stats['average_processing_time']
        new_avg = ((current_avg * (total_successful - 1)) + result.processing_time) / total_successful
        self.stats['average_processing_time'] = new_avg
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            'total_queries': self.stats['total_queries'],
            'successful_queries': self.stats['successful_queries'],
            'failed_queries': self.stats['failed_queries'],
            'success_rate': (self.stats['successful_queries'] / max(1, self.stats['total_queries'])) * 100,
            'average_processing_time': self.stats['average_processing_time'],
            'queue_size': self.query_queue.qsize(),
            'processing': self.processing
        }
    
    def stop_processing(self):
        """Stop query processing"""
        self.processing = False
        logger.info("Query processing stopped")
    
    def clear_queue(self):
        """Clear the query queue"""
        while not self.query_queue.empty():
            try:
                self.query_queue.get_nowait()
            except Empty:
                break
        logger.info("Query queue cleared")
