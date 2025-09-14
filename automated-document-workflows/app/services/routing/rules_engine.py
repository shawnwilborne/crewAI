"""
YAML-based routing rules engine for document processing.
"""

import os
import re
import yaml
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session
from pyzbar import pyzbar
from PIL import Image

from app.db.models import Document, Rule, Route
from app.utils.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RoutingEngine:
    """YAML-based document routing and rule processing engine."""
    
    def __init__(self, db: Session):
        self.db = db
        self.rules_cache = {}
        self.rules_cache_time = None
        
    def load_rules_from_yaml(self, rules_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Load routing rules from YAML file.
        
        Args:
            rules_file: Path to rules file (uses default if None)
            
        Returns:
            Dictionary of loaded rules
        """
        
        if rules_file is None:
            rules_file = os.path.join(settings.rules_dir, "routing.yaml")
        
        if not Path(rules_file).exists():
            logger.warning(f"Rules file not found: {rules_file}")
            return {}
        
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                rules_data = yaml.safe_load(f)
            
            # Validate rules structure
            if not isinstance(rules_data, dict) or 'rules' not in rules_data:
                raise ValueError("Invalid rules file structure - missing 'rules' key")
            
            logger.info(f"Loaded {len(rules_data['rules'])} rules from {rules_file}")
            
            # Cache rules with file hash
            file_hash = self._calculate_file_hash(rules_file)
            self.rules_cache = {
                'rules': rules_data['rules'],
                'file_hash': file_hash,
                'load_time': datetime.utcnow()
            }
            
            # Update database with rules
            self._sync_rules_to_db(rules_data['rules'], rules_file, file_hash)
            
            return rules_data
            
        except Exception as e:
            logger.error(f"Failed to load rules from {rules_file}: {e}")
            raise e
    
    def _sync_rules_to_db(self, rules_data: List[Dict[str, Any]], source_file: str, file_hash: str):
        """Synchronize rules from YAML to database."""
        
        try:
            for rule_config in rules_data:
                rule_name = rule_config.get('name')
                if not rule_name:
                    logger.warning("Rule without name found, skipping")
                    continue
                
                # Check if rule exists
                existing_rule = self.db.query(Rule).filter(Rule.name == rule_name).first()
                
                if existing_rule:
                    # Update existing rule if hash changed
                    if existing_rule.source_hash != file_hash:
                        existing_rule.description = rule_config.get('description', '')
                        existing_rule.conditions = rule_config.get('conditions', [])
                        existing_rule.actions = rule_config.get('actions', {})
                        existing_rule.priority = rule_config.get('priority', 0)
                        existing_rule.enabled = rule_config.get('enabled', True)
                        existing_rule.source_file = source_file
                        existing_rule.source_hash = file_hash
                        logger.debug(f"Updated rule: {rule_name}")
                else:
                    # Create new rule
                    new_rule = Rule(
                        name=rule_name,
                        description=rule_config.get('description', ''),
                        conditions=rule_config.get('conditions', []),
                        actions=rule_config.get('actions', {}),
                        priority=rule_config.get('priority', 0),
                        enabled=rule_config.get('enabled', True),
                        source_file=source_file,
                        source_hash=file_hash,
                    )
                    self.db.add(new_rule)
                    logger.debug(f"Created rule: {rule_name}")
            
            self.db.commit()
            logger.info("Rules synchronized to database")
            
        except Exception as e:
            logger.error(f"Failed to sync rules to database: {e}")
            self.db.rollback()
    
    def apply_routing_rules(
        self,
        document: Document,
        rule_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Apply routing rules to a document.
        
        Args:
            document: Document to route
            rule_names: Specific rules to apply (all if None)
            
        Returns:
            Routing results
        """
        
        logger.info(f"Applying routing rules to document {document.id}")
        
        try:
            # Load rules if not cached or outdated
            if not self._rules_cache_valid():
                self.load_rules_from_yaml()
            
            # Get rules from database (more reliable than cache)
            query = self.db.query(Rule).filter(Rule.enabled == True)
            
            if rule_names:
                query = query.filter(Rule.name.in_(rule_names))
            
            rules = query.order_by(Rule.priority.desc(), Rule.name).all()
            
            if not rules:
                logger.info("No routing rules found")
                return {"matched_rules": 0, "routes_created": 0}
            
            # Extract document context for rule evaluation
            context = self._extract_document_context(document)
            
            matched_rules = 0
            routes_created = 0
            
            # Apply each rule
            for rule in rules:
                try:
                    if self._evaluate_rule_conditions(rule, context):
                        route = self._create_route(document, rule, context)
                        if route:
                            routes_created += 1
                            
                            # Update rule statistics
                            rule.matched_count += 1
                            rule.last_matched_at = datetime.utcnow()
                            
                        matched_rules += 1
                        logger.info(f"Rule matched: {rule.name}")
                        
                        # Stop at first match unless configured otherwise
                        if not rule.actions.get('continue_matching', False):
                            break
                            
                except Exception as e:
                    logger.error(f"Error applying rule {rule.name}: {e}")
                    continue
            
            self.db.commit()
            
            return {
                "matched_rules": matched_rules,
                "routes_created": routes_created,
                "total_rules_evaluated": len(rules)
            }
            
        except Exception as e:
            logger.error(f"Routing rules application failed: {e}")
            return {"error": str(e), "matched_rules": 0, "routes_created": 0}
    
    def _extract_document_context(self, document: Document) -> Dict[str, Any]:
        """Extract context information from document for rule evaluation."""
        
        context = {
            'filename': document.filename,
            'original_filename': document.original_filename,
            'file_path': document.file_path,
            'file_size': document.file_size,
            'mime_type': document.mime_type,
            'extracted_text': document.extracted_text or '',
            'page_count': document.page_count,
            'has_text': document.has_text,
            'language': document.language,
            'created_at': document.created_at,
            'file_extension': Path(document.filename).suffix.lower().lstrip('.'),
        }
        
        # Add text analysis
        if document.extracted_text:
            text = document.extracted_text.lower()
            context.update({
                'word_count': len(document.extracted_text.split()),
                'character_count': len(document.extracted_text),
                'contains_digits': bool(re.search(r'\d', document.extracted_text)),
                'contains_email': bool(re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', document.extracted_text)),
                'contains_phone': bool(re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', document.extracted_text)),
                'contains_date': bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', document.extracted_text)),
                'contains_currency': bool(re.search(r'[\$£€¥]\s*\d+', document.extracted_text)),
            })
        
        # Try to detect barcodes/QR codes if image-based
        if document.mime_type.startswith('image/'):
            context['barcode_data'] = self._extract_barcode_data(document.file_path)
        
        return context
    
    def _evaluate_rule_conditions(self, rule: Rule, context: Dict[str, Any]) -> bool:
        """Evaluate if rule conditions match the document context."""
        
        conditions = rule.conditions
        if not conditions:
            return True  # No conditions = always match
        
        # All conditions must match (AND logic)
        for condition in conditions:
            if not self._evaluate_single_condition(condition, context):
                return False
        
        return True
    
    def _evaluate_single_condition(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate a single condition against context."""
        
        condition_type = condition.get('type', '').lower()
        condition_value = condition.get('value', '')
        operator = condition.get('operator', 'equals').lower()
        case_sensitive = condition.get('case_sensitive', False)
        
        # Get the context value to check
        if condition_type == 'filename_regex':
            test_value = context.get('filename', '')
            return self._match_regex(condition_value, test_value, case_sensitive)
            
        elif condition_type == 'filename_contains':
            test_value = context.get('filename', '')
            return self._match_contains(condition_value, test_value, case_sensitive)
            
        elif condition_type == 'mime_type':
            test_value = context.get('mime_type', '')
            return self._match_value(condition_value, test_value, operator, case_sensitive)
            
        elif condition_type == 'file_extension':
            test_value = context.get('file_extension', '')
            return self._match_value(condition_value, test_value, operator, case_sensitive)
            
        elif condition_type == 'keywords':
            test_value = context.get('extracted_text', '')
            keywords = condition_value if isinstance(condition_value, list) else [condition_value]
            return self._match_keywords(keywords, test_value, case_sensitive, operator)
            
        elif condition_type == 'file_size':
            test_value = context.get('file_size', 0)
            return self._match_numeric(condition_value, test_value, operator)
            
        elif condition_type == 'page_count':
            test_value = context.get('page_count', 0)
            return self._match_numeric(condition_value, test_value, operator)
            
        elif condition_type == 'has_text':
            test_value = context.get('has_text', False)
            return test_value == bool(condition_value)
            
        elif condition_type == 'language':
            test_value = context.get('language', '')
            return self._match_value(condition_value, test_value, operator, case_sensitive)
            
        elif condition_type == 'contains_barcode':
            barcode_data = context.get('barcode_data', [])
            return len(barcode_data) > 0 if condition_value else len(barcode_data) == 0
            
        elif condition_type == 'barcode_value':
            barcode_data = context.get('barcode_data', [])
            barcode_texts = [item['data'] for item in barcode_data]
            return self._match_keywords([condition_value], ' '.join(barcode_texts), case_sensitive, 'contains')
            
        elif condition_type == 'date_range':
            # Match documents created within a date range
            doc_date = context.get('created_at')
            if not doc_date:
                return False
            
            start_date = condition.get('start_date')
            end_date = condition.get('end_date')
            
            if start_date and doc_date < start_date:
                return False
            if end_date and doc_date > end_date:
                return False
                
            return True
            
        else:
            logger.warning(f"Unknown condition type: {condition_type}")
            return False
    
    def _match_regex(self, pattern: str, text: str, case_sensitive: bool) -> bool:
        """Match text against regex pattern."""
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            return bool(re.search(pattern, text, flags))
        except re.error as e:
            logger.error(f"Invalid regex pattern '{pattern}': {e}")
            return False
    
    def _match_contains(self, search_text: str, target_text: str, case_sensitive: bool) -> bool:
        """Check if target text contains search text."""
        if not case_sensitive:
            search_text = search_text.lower()
            target_text = target_text.lower()
        
        return search_text in target_text
    
    def _match_value(self, condition_value: str, test_value: str, operator: str, case_sensitive: bool) -> bool:
        """Match values with specified operator."""
        if not case_sensitive:
            condition_value = condition_value.lower()
            test_value = test_value.lower()
        
        if operator == 'equals':
            return condition_value == test_value
        elif operator == 'not_equals':
            return condition_value != test_value
        elif operator == 'contains':
            return condition_value in test_value
        elif operator == 'not_contains':
            return condition_value not in test_value
        elif operator == 'starts_with':
            return test_value.startswith(condition_value)
        elif operator == 'ends_with':
            return test_value.endswith(condition_value)
        else:
            logger.warning(f"Unknown operator: {operator}")
            return False
    
    def _match_keywords(self, keywords: List[str], text: str, case_sensitive: bool, operator: str) -> bool:
        """Match keywords against text."""
        if not case_sensitive:
            text = text.lower()
            keywords = [kw.lower() for kw in keywords]
        
        if operator in ['contains', 'any']:
            return any(keyword in text for keyword in keywords)
        elif operator == 'all':
            return all(keyword in text for keyword in keywords)
        elif operator == 'none':
            return not any(keyword in text for keyword in keywords)
        else:
            # Default to 'any'
            return any(keyword in text for keyword in keywords)
    
    def _match_numeric(self, condition_value: Any, test_value: float, operator: str) -> bool:
        """Match numeric values with operator."""
        try:
            condition_value = float(condition_value)
        except (ValueError, TypeError):
            return False
        
        if operator == 'equals':
            return test_value == condition_value
        elif operator == 'greater_than':
            return test_value > condition_value
        elif operator == 'less_than':
            return test_value < condition_value
        elif operator == 'greater_equal':
            return test_value >= condition_value
        elif operator == 'less_equal':
            return test_value <= condition_value
        else:
            return test_value == condition_value
    
    def _extract_barcode_data(self, image_path: str) -> List[Dict[str, Any]]:
        """Extract barcode/QR code data from image."""
        
        try:
            image = Image.open(image_path)
            barcodes = pyzbar.decode(image)
            
            result = []
            for barcode in barcodes:
                result.append({
                    'type': barcode.type,
                    'data': barcode.data.decode('utf-8'),
                    'rect': barcode.rect,
                    'quality': barcode.quality if hasattr(barcode, 'quality') else None
                })
            
            return result
            
        except Exception as e:
            logger.warning(f"Barcode extraction failed for {image_path}: {e}")
            return []
    
    def _create_route(self, document: Document, rule: Rule, context: Dict[str, Any]) -> Optional[Route]:
        """Create a route based on matched rule."""
        
        try:
            actions = rule.actions
            destination = actions.get('destination', '')
            rename_template = actions.get('rename_template', '')
            
            # Process template placeholders in destination and rename template
            processed_destination = self._process_template(destination, context)
            processed_rename_template = self._process_template(rename_template, context) if rename_template else None
            
            # Generate final filename if rename template provided
            final_filename = None
            if processed_rename_template:
                file_extension = context.get('file_extension', '')
                if file_extension and not processed_rename_template.endswith(f'.{file_extension}'):
                    final_filename = f"{processed_rename_template}.{file_extension}"
                else:
                    final_filename = processed_rename_template
            
            # Create route record
            route = Route(
                document_id=document.id,
                rule_name=rule.name,
                matched_conditions={
                    'rule_conditions': rule.conditions,
                    'context_used': {k: v for k, v in context.items() if k in ['filename', 'mime_type', 'file_size', 'page_count']}
                },
                destination=processed_destination,
                rename_template=processed_rename_template,
                final_filename=final_filename,
                applied=False,  # Will be applied later
            )
            
            self.db.add(route)
            self.db.flush()  # Get the ID
            
            logger.info(f"Created route for document {document.id} using rule {rule.name}")
            
            return route
            
        except Exception as e:
            logger.error(f"Failed to create route: {e}")
            return None
    
    def _process_template(self, template: str, context: Dict[str, Any]) -> str:
        """Process template placeholders with context data."""
        
        if not template:
            return template
        
        # Define available placeholders
        placeholders = {
            'date_yyyy_mm_dd': datetime.now().strftime('%Y-%m-%d'),
            'date_yyyy': datetime.now().strftime('%Y'),
            'date_mm': datetime.now().strftime('%m'),
            'date_dd': datetime.now().strftime('%d'),
            'time_hh_mm_ss': datetime.now().strftime('%H-%M-%S'),
            'filename': Path(context.get('filename', 'document')).stem,
            'original_filename': Path(context.get('original_filename', 'document')).stem,
            'extension': context.get('file_extension', ''),
            'mime_type': context.get('mime_type', '').replace('/', '_'),
            'file_size_mb': str(round(context.get('file_size', 0) / (1024 * 1024), 2)),
            'page_count': str(context.get('page_count', 0)),
            'language': context.get('language', 'unknown'),
        }
        
        # Process template
        result = template
        
        for placeholder, value in placeholders.items():
            # Handle simple placeholders
            result = result.replace(f'{{{placeholder}}}', str(value))
            
            # Handle counter placeholders with padding
            counter_match = re.search(r'\{counter:(\d+)\}', result)
            if counter_match:
                padding = int(counter_match.group(1))
                counter_value = self._get_next_counter_value(padding)
                result = result.replace(counter_match.group(0), counter_value)
        
        return result
    
    def _get_next_counter_value(self, padding: int = 6) -> str:
        """Get next counter value for document numbering."""
        
        # This would integrate with the SequenceCounter model
        # For now, return a simple timestamp-based counter
        import time
        counter = int(time.time() % 1000000)  # Last 6 digits of timestamp
        return str(counter).zfill(padding)
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate hash of file for change detection."""
        
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            return hashlib.sha256(content).hexdigest()
            
        except Exception as e:
            logger.error(f"Failed to calculate file hash: {e}")
            return ""
    
    def _rules_cache_valid(self) -> bool:
        """Check if rules cache is still valid."""
        
        if not self.rules_cache or not self.rules_cache_time:
            return False
        
        # Cache valid for 5 minutes
        cache_age = (datetime.utcnow() - self.rules_cache_time).total_seconds()
        return cache_age < 300
    
    def test_rule(
        self,
        rule_config: Dict[str, Any],
        test_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Test a rule configuration against test context.
        
        Args:
            rule_config: Rule configuration to test
            test_context: Test context data
            
        Returns:
            Test results
        """
        
        try:
            conditions = rule_config.get('conditions', [])
            
            # Evaluate each condition
            condition_results = []
            
            for i, condition in enumerate(conditions):
                result = self._evaluate_single_condition(condition, test_context)
                condition_results.append({
                    'condition_index': i,
                    'condition': condition,
                    'matched': result
                })
            
            # Overall match (all conditions must pass)
            overall_match = all(cr['matched'] for cr in condition_results)
            
            return {
                'rule_name': rule_config.get('name', 'test_rule'),
                'overall_match': overall_match,
                'condition_results': condition_results,
                'actions': rule_config.get('actions', {}),
                'test_context': test_context
            }
            
        except Exception as e:
            logger.error(f"Rule test failed: {e}")
            return {
                'error': str(e),
                'overall_match': False,
                'condition_results': [],
                'actions': {},
                'test_context': test_context
            }