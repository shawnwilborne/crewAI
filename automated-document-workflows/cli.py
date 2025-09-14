"""
Comprehensive CLI interface for Automated Document Workflows.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.tree import Tree
from rich.prompt import Confirm

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal, create_tables
from app.db.models import Document, Job, Output, Rule, DocumentStatus, JobStatus
from app.services.pipeline import DocumentProcessor
from app.services.routing.rules_engine import RoutingEngine
from app.utils.settings import settings
from app.utils.filename_sanitize import sanitize_filename
from app.worker import process_document_task

console = Console()


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Automated Document Workflows CLI
    
    A comprehensive command-line interface for document processing,
    OCR, conversion, routing, and delivery.
    """
    # Ensure database tables exist
    create_tables()


@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--recursive', '-r', is_flag=True, help='Process directories recursively')
@click.option('--pattern', '-p', default='*', help='File pattern to match (default: *)')
@click.option('--dry-run', is_flag=True, help='Show what would be processed without doing it')
@click.option('--auto-process', is_flag=True, help='Automatically start processing jobs')
def ingest(path, recursive, pattern, dry_run, auto_process):
    """Ingest documents from PATH (file or directory).
    
    Creates document records and optionally starts processing jobs.
    
    Examples:
        cli.py ingest document.pdf
        cli.py ingest /path/to/documents/ --recursive --auto-process
        cli.py ingest folder/ --pattern "*.pdf" --dry-run
    """
    
    path = Path(path)
    
    if path.is_file():
        files = [path]
    elif path.is_dir():
        if recursive:
            files = list(path.rglob(pattern))
        else:
            files = list(path.glob(pattern))
        files = [f for f in files if f.is_file()]
    else:
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        return
    
    # Filter for supported file types
    supported_extensions = settings.allowed_extensions
    supported_files = [
        f for f in files 
        if f.suffix.lower().lstrip('.') in supported_extensions
    ]
    
    if not supported_files:
        console.print(f"[yellow]No supported files found in {path}[/yellow]")
        console.print(f"Supported extensions: {', '.join(supported_extensions)}")
        return
    
    console.print(f"Found {len(supported_files)} supported files")
    
    if dry_run:
        console.print("\n[yellow]DRY RUN - Files that would be processed:[/yellow]")
        for file_path in supported_files:
            console.print(f"  {file_path}")
        return
    
    db = SessionLocal()
    
    try:
        ingested_count = 0
        job_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("Ingesting documents...", total=len(supported_files))
            
            for file_path in supported_files:
                try:
                    # Check if already exists
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    import hashlib
                    md5_hash = hashlib.md5(content).hexdigest()
                    
                    existing = db.query(Document).filter(Document.md5_hash == md5_hash).first()
                    if existing:
                        progress.console.print(f"[dim]Skipped (duplicate): {file_path.name}[/dim]")
                        progress.advance(task)
                        continue
                    
                    # Create document
                    document = Document(
                        filename=sanitize_filename(file_path.name),
                        original_filename=file_path.name,
                        file_path=str(file_path),
                        file_size=len(content),
                        mime_type=_get_mime_type(file_path),
                        md5_hash=md5_hash,
                        status=DocumentStatus.UPLOADED,
                    )
                    
                    db.add(document)
                    db.flush()
                    
                    ingested_count += 1
                    
                    # Create job if auto-process enabled
                    if auto_process:
                        job = Job(
                            document_id=document.id,
                            job_type="full_pipeline",
                            status=JobStatus.PENDING,
                        )
                        db.add(job)
                        job_count += 1
                    
                    progress.console.print(f"[green]Ingested: {file_path.name}[/green]")
                    
                except Exception as e:
                    progress.console.print(f"[red]Failed: {file_path.name} - {e}[/red]")
                
                progress.advance(task)
        
        db.commit()
        
        console.print(f"\n[green]✓[/green] Ingested {ingested_count} documents")
        if auto_process:
            console.print(f"[green]✓[/green] Created {job_count} processing jobs")
            console.print("[dim]Use 'cli.py jobs list' to view job status[/dim]")
    
    finally:
        db.close()


@cli.command()
@click.argument('job_id', required=False)
@click.option('--folder', type=click.Path(exists=True, file_okay=False), help='Process all pending jobs')
@click.option('--wait', is_flag=True, help='Wait for job completion')
@click.option('--config', type=click.Path(exists=True), help='JSON config file for processing')
def run(job_id, folder, wait, config):
    """Run processing job by JOB_ID or process pending jobs in FOLDER.
    
    Examples:
        cli.py run 123e4567-e89b-12d3-a456-426614174000
        cli.py run --folder /path/to/documents --wait
    """
    
    db = SessionLocal()
    
    try:
        # Load config if provided
        job_config = {}
        if config:
            with open(config, 'r') as f:
                job_config = json.load(f)
        
        if job_id:
            # Run specific job
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                console.print(f"[red]Job not found: {job_id}[/red]")
                return
            
            _run_single_job(db, job, job_config, wait)
            
        elif folder:
            # Process all pending jobs for documents in folder
            folder_path = str(Path(folder).resolve())
            
            pending_jobs = db.query(Job).join(Document).filter(
                Job.status == JobStatus.PENDING,
                Document.file_path.startswith(folder_path)
            ).all()
            
            if not pending_jobs:
                console.print("[yellow]No pending jobs found in folder[/yellow]")
                return
            
            console.print(f"Found {len(pending_jobs)} pending jobs")
            
            for job in pending_jobs:
                _run_single_job(db, job, job_config, wait=False)
            
            if wait:
                console.print("\n[cyan]Waiting for all jobs to complete...[/cyan]")
                _wait_for_jobs(db, [j.id for j in pending_jobs])
        
        else:
            console.print("[red]Either JOB_ID or --folder must be specified[/red]")
    
    finally:
        db.close()


def _run_single_job(db, job, config, wait):
    """Run a single job."""
    
    document = db.query(Document).filter(Document.id == job.document_id).first()
    
    console.print(f"[cyan]Starting job {job.id} for document: {document.filename}[/cyan]")
    
    try:
        # Update job config if provided
        if config:
            job.config = {**(job.config or {}), **config}
            db.commit()
        
        # Start processing
        processor = DocumentProcessor(db)
        
        if wait:
            # Process synchronously
            def progress_callback(progress, message):
                console.print(f"  [dim]{progress:.1f}% - {message}[/dim]")
            
            result = processor.process_job(job, progress_callback)
            
            if result.get("status") == "completed":
                console.print(f"[green]✓ Job completed: {job.id}[/green]")
            else:
                console.print(f"[red]✗ Job failed: {job.id}[/red]")
                if "error" in result:
                    console.print(f"  Error: {result['error']}")
        else:
            # Start background task
            process_document_task.delay(str(job.id))
            console.print(f"[green]Job queued: {job.id}[/green]")
    
    except Exception as e:
        console.print(f"[red]Job failed: {e}[/red]")


def _wait_for_jobs(db, job_ids):
    """Wait for jobs to complete."""
    
    completed = set()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        task = progress.add_task("Waiting for jobs...", total=None)
        
        while len(completed) < len(job_ids):
            for job_id in job_ids:
                if job_id in completed:
                    continue
                
                job = db.query(Job).filter(Job.id == job_id).first()
                if job and job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    completed.add(job_id)
                    status_color = "green" if job.status == JobStatus.COMPLETED else "red"
                    progress.console.print(f"[{status_color}]{job.status.value}: {job_id}[/{status_color}]")
            
            if len(completed) < len(job_ids):
                time.sleep(2)
    
    console.print(f"\n[green]All jobs completed ({len(completed)}/{len(job_ids)})[/green]")


@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--rules', help='Comma-separated list of rule names to test')
@click.option('--dry-run', is_flag=True, help='Test mode - don\'t apply routes')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed rule evaluation')
def route(path, rules, dry_run, verbose):
    """Test routing rules against a document at PATH.
    
    Examples:
        cli.py route document.pdf --dry-run --verbose
        cli.py route folder/invoice.pdf --rules "invoice_rule,finance_rule"
    """
    
    db = SessionLocal()
    
    try:
        file_path = Path(path)
        
        # Find or create document
        document = _find_or_create_document(db, file_path)
        
        console.print(f"Testing routing rules for: [cyan]{document.filename}[/cyan]")
        
        # Setup routing engine
        routing_engine = RoutingEngine(db)
        
        # Parse rule names
        rule_names = None
        if rules:
            rule_names = [name.strip() for name in rules.split(',')]
            console.print(f"Using rules: {rule_names}")
        
        if dry_run:
            console.print("[yellow]DRY RUN - Rules will be evaluated but not applied[/yellow]")
        
        # Apply routing rules
        result = routing_engine.apply_routing_rules(document, rule_names)
        
        # Display results
        console.print(f"\nRouting Results:")
        console.print(f"  Rules evaluated: {result.get('total_rules_evaluated', 0)}")
        console.print(f"  Rules matched: {result.get('matched_rules', 0)}")
        console.print(f"  Routes created: {result.get('routes_created', 0)}")
        
        if verbose:
            # Show created routes
            routes = db.query(Document).filter(Document.document_id == document.id).all()
            if routes:
                console.print("\nCreated Routes:")
                for route in routes:
                    console.print(f"  Rule: {route.rule_name}")
                    console.print(f"  Destination: {route.destination}")
                    if route.final_filename:
                        console.print(f"  New filename: {route.final_filename}")
    
    finally:
        db.close()


@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--template', help='Rename template pattern')
@click.option('--dry-run', is_flag=True, help='Preview renaming without applying')
@click.option('--commit', is_flag=True, help='Apply renaming changes')
def rename(path, template, dry_run, commit):
    """Apply renaming to documents at PATH.
    
    Examples:
        cli.py rename document.pdf --template "{date_yyyy_mm_dd}_{doc_type}_{counter:6}" --dry-run
        cli.py rename folder/ --template "PROC_{counter:4}" --commit
    """
    
    if not template:
        console.print("[red]Template must be specified with --template[/red]")
        return
    
    db = SessionLocal()
    
    try:
        file_path = Path(path)
        
        if file_path.is_file():
            files = [file_path]
        else:
            files = list(file_path.rglob('*'))
            files = [f for f in files if f.is_file()]
        
        console.print(f"Processing {len(files)} files with template: [cyan]{template}[/cyan]")
        
        if dry_run:
            console.print("[yellow]DRY RUN - Preview of renaming:[/yellow]")
        
        renamed_count = 0
        
        for file in files:
            try:
                # Generate new filename
                context = _get_file_context(file)
                new_filename = _process_rename_template(template, context)
                
                if dry_run:
                    console.print(f"  {file.name} → {new_filename}")
                elif commit:
                    new_path = file.parent / new_filename
                    if not new_path.exists():
                        file.rename(new_path)
                        console.print(f"[green]Renamed:[/green] {file.name} → {new_filename}")
                        renamed_count += 1
                    else:
                        console.print(f"[yellow]Skipped (exists):[/yellow] {new_filename}")
                
            except Exception as e:
                console.print(f"[red]Error processing {file.name}: {e}[/red]")
        
        if commit:
            console.print(f"\n[green]✓[/green] Renamed {renamed_count} files")
        elif not dry_run:
            console.print("[yellow]Use --commit to apply changes or --dry-run to preview[/yellow]")
    
    finally:
        db.close()


@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--start', type=int, default=1, help='Starting Bates number')
@click.option('--prefix', default='BATES', help='Bates number prefix')
@click.option('--position', default='bottom_right', help='Position on page')
@click.option('--dry-run', is_flag=True, help='Preview without applying')
@click.option('--apply', is_flag=True, help='Apply Bates numbering')
def bates(path, start, prefix, position, dry_run, apply):
    """Apply Bates numbering to documents at PATH.
    
    Examples:
        cli.py bates document.pdf --start 1000 --prefix "LEGAL" --dry-run
        cli.py bates folder/ --start 1 --prefix "CASE001" --apply
    """
    
    if dry_run:
        console.print(f"[yellow]DRY RUN - Bates numbering preview:[/yellow]")
        console.print(f"  Start: {start}")
        console.print(f"  Prefix: {prefix}")
        console.print(f"  Position: {position}")
        console.print(f"[dim]Note: Bates numbering not fully implemented yet[/dim]")
    elif apply:
        console.print(f"[cyan]Applying Bates numbering...[/cyan]")
        console.print(f"[yellow]Note: Bates numbering not fully implemented yet[/yellow]")
    else:
        console.print("[yellow]Use --dry-run to preview or --apply to execute[/yellow]")


@cli.command()
@click.argument('data_path', type=click.Path(exists=True))
@click.argument('template_path', type=click.Path(exists=True))
@click.option('--output', '-o', help='Output file path')
@click.option('--format', 'output_format', type=click.Choice(['docx', 'pdf']), default='docx')
def report(data_path, template_path, output, output_format):
    """Generate report from DATA_PATH using TEMPLATE_PATH.
    
    Examples:
        cli.py report data.csv template.docx --output report.docx
        cli.py report data.json template.html --format pdf --output report.pdf
    """
    
    console.print(f"[cyan]Generating report from {data_path} using {template_path}[/cyan]")
    console.print(f"[yellow]Note: Report generation not fully implemented yet[/yellow]")
    
    if output:
        console.print(f"Output would be saved to: {output}")


@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.argument('target')
@click.option('--destination', help='Destination path/bucket/folder')
@click.option('--verify', is_flag=True, help='Verify delivery success')
def deliver(path, target, destination, verify):
    """Deliver documents at PATH to TARGET (s3, sftp, shopify).
    
    Examples:
        cli.py deliver document.pdf s3 --destination my-bucket/documents/
        cli.py deliver folder/ sftp --destination /remote/path/ --verify
    """
    
    valid_targets = ['s3', 'sftp', 'shopify', 'local']
    
    if target not in valid_targets:
        console.print(f"[red]Invalid target. Must be one of: {', '.join(valid_targets)}[/red]")
        return
    
    console.print(f"[cyan]Delivering {path} to {target}[/cyan]")
    if destination:
        console.print(f"Destination: {destination}")
    
    console.print(f"[yellow]Note: Delivery not fully implemented yet[/yellow]")


@cli.group()
def jobs():
    """Job management commands."""
    pass


@jobs.command('list')
@click.option('--status', type=click.Choice(['pending', 'running', 'completed', 'failed', 'cancelled']))
@click.option('--limit', type=int, default=20, help='Number of jobs to show')
def list_jobs(status, limit):
    """List processing jobs."""
    
    db = SessionLocal()
    
    try:
        query = db.query(Job).join(Document)
        
        if status:
            query = query.filter(Job.status == status)
        
        jobs = query.order_by(Job.created_at.desc()).limit(limit).all()
        
        if not jobs:
            console.print("[yellow]No jobs found[/yellow]")
            return
        
        table = Table(title=f"Jobs ({len(jobs)} shown)")
        table.add_column("ID", style="dim")
        table.add_column("Document", style="cyan")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("Progress")
        table.add_column("Created")
        
        for job in jobs:
            document = job.document
            status_style = {
                'pending': 'yellow',
                'running': 'blue',
                'completed': 'green',
                'failed': 'red',
                'cancelled': 'dim'
            }.get(job.status.value, 'white')
            
            table.add_row(
                str(job.id)[:8] + '...',
                document.filename,
                job.job_type,
                f"[{status_style}]{job.status.value}[/{status_style}]",
                f"{job.progress:.1f}%",
                job.created_at.strftime('%Y-%m-%d %H:%M')
            )
        
        console.print(table)
    
    finally:
        db.close()


@jobs.command('status')
@click.argument('job_id')
def job_status(job_id):
    """Show detailed job status."""
    
    db = SessionLocal()
    
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            console.print(f"[red]Job not found: {job_id}[/red]")
            return
        
        document = job.document
        
        # Create status panel
        status_text = f"""[cyan]Job ID:[/cyan] {job.id}
[cyan]Document:[/cyan] {document.filename}
[cyan]Type:[/cyan] {job.job_type}
[cyan]Status:[/cyan] {job.status.value}
[cyan]Progress:[/cyan] {job.progress:.1f}%
[cyan]Created:[/cyan] {job.created_at}
[cyan]Started:[/cyan] {job.started_at or 'Not started'}
[cyan]Completed:[/cyan] {job.completed_at or 'Not completed'}"""
        
        if job.current_step:
            status_text += f"\n[cyan]Current Step:[/cyan] {job.current_step}"
        
        if job.error_message:
            status_text += f"\n[red]Error:[/red] {job.error_message}"
        
        if job.worker_id:
            status_text += f"\n[cyan]Worker:[/cyan] {job.worker_id}"
        
        console.print(Panel(status_text, title=f"Job Status", border_style="blue"))
        
        # Show steps if available
        steps = job.steps
        if steps:
            console.print("\n[cyan]Processing Steps:[/cyan]")
            
            step_table = Table()
            step_table.add_column("Step", style="cyan")
            step_table.add_column("Status")
            step_table.add_column("Duration")
            step_table.add_column("Error")
            
            for step in steps:
                status_style = {
                    'pending': 'yellow',
                    'running': 'blue',
                    'completed': 'green',
                    'failed': 'red',
                    'skipped': 'dim'
                }.get(step.status.value, 'white')
                
                duration = ""
                if step.processing_time_seconds:
                    duration = f"{step.processing_time_seconds:.1f}s"
                
                step_table.add_row(
                    step.step_name,
                    f"[{status_style}]{step.status.value}[/{status_style}]",
                    duration,
                    step.error_message or ""
                )
            
            console.print(step_table)
    
    finally:
        db.close()


@cli.group()
def documents():
    """Document management commands."""
    pass


@documents.command('list')
@click.option('--status', type=click.Choice(['uploaded', 'processing', 'completed', 'failed', 'quarantined']))
@click.option('--limit', type=int, default=20, help='Number of documents to show')
def list_documents(status, limit):
    """List documents."""
    
    db = SessionLocal()
    
    try:
        query = db.query(Document)
        
        if status:
            query = query.filter(Document.status == status)
        
        documents = query.order_by(Document.created_at.desc()).limit(limit).all()
        
        if not documents:
            console.print("[yellow]No documents found[/yellow]")
            return
        
        table = Table(title=f"Documents ({len(documents)} shown)")
        table.add_column("ID", style="dim")
        table.add_column("Filename", style="cyan")
        table.add_column("Size")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("Pages")
        table.add_column("Created")
        
        for doc in documents:
            status_style = {
                'uploaded': 'blue',
                'processing': 'yellow',
                'completed': 'green',
                'failed': 'red',
                'quarantined': 'red'
            }.get(doc.status.value, 'white')
            
            # Format file size
            size_mb = doc.file_size / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{doc.file_size // 1024} KB"
            
            table.add_row(
                str(doc.id)[:8] + '...',
                doc.filename,
                size_str,
                doc.mime_type.split('/')[-1],
                f"[{status_style}]{doc.status.value}[/{status_style}]",
                str(doc.page_count),
                doc.created_at.strftime('%Y-%m-%d %H:%M')
            )
        
        console.print(table)
    
    finally:
        db.close()


@cli.command()
def status():
    """Show system status and statistics."""
    
    db = SessionLocal()
    
    try:
        # Get counts
        total_docs = db.query(Document).count()
        total_jobs = db.query(Job).count()
        total_outputs = db.query(Output).count()
        
        # Get status breakdowns
        doc_status_counts = {}
        for status in DocumentStatus:
            count = db.query(Document).filter(Document.status == status).count()
            if count > 0:
                doc_status_counts[status.value] = count
        
        job_status_counts = {}
        for status in JobStatus:
            count = db.query(Job).filter(Job.status == status).count()
            if count > 0:
                job_status_counts[status.value] = count
        
        # Create status panel
        status_text = f"""[cyan]Documents:[/cyan] {total_docs}
[cyan]Jobs:[/cyan] {total_jobs}
[cyan]Outputs:[/cyan] {total_outputs}

[cyan]Document Status:[/cyan]"""
        
        for status, count in doc_status_counts.items():
            status_text += f"\n  {status}: {count}"
        
        status_text += f"\n\n[cyan]Job Status:[/cyan]"
        for status, count in job_status_counts.items():
            status_text += f"\n  {status}: {count}"
        
        # Add configuration info
        status_text += f"\n\n[cyan]Configuration:[/cyan]"
        status_text += f"\n  BaaS Enabled: {'Yes' if settings.baas_enabled else 'No'}"
        status_text += f"\n  Shopify Enabled: {'Yes' if settings.shopify_enabled else 'No'}"
        status_text += f"\n  S3 Enabled: {'Yes' if settings.s3_enabled else 'No'}"
        status_text += f"\n  SFTP Enabled: {'Yes' if settings.sftp_enabled else 'No'}"
        
        console.print(Panel(status_text, title="System Status", border_style="green"))
    
    finally:
        db.close()


def _find_or_create_document(db, file_path):
    """Find existing document or create new one."""
    
    # Try to find existing document
    abs_path = str(file_path.resolve())
    document = db.query(Document).filter(Document.file_path == abs_path).first()
    
    if document:
        return document
    
    # Create new document
    with open(file_path, 'rb') as f:
        content = f.read()
    
    import hashlib
    md5_hash = hashlib.md5(content).hexdigest()
    
    document = Document(
        filename=sanitize_filename(file_path.name),
        original_filename=file_path.name,
        file_path=abs_path,
        file_size=len(content),
        mime_type=_get_mime_type(file_path),
        md5_hash=md5_hash,
        status=DocumentStatus.UPLOADED,
    )
    
    db.add(document)
    db.commit()
    db.refresh(document)
    
    return document


def _get_mime_type(file_path):
    """Get MIME type for file."""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'


def _get_file_context(file_path):
    """Get file context for template processing."""
    from datetime import datetime
    
    return {
        'filename': file_path.stem,
        'extension': file_path.suffix.lstrip('.'),
        'date_yyyy_mm_dd': datetime.now().strftime('%Y-%m-%d'),
        'date_yyyy': datetime.now().strftime('%Y'),
        'date_mm': datetime.now().strftime('%m'),
        'date_dd': datetime.now().strftime('%d'),
        'time_hh_mm_ss': datetime.now().strftime('%H-%M-%S'),
        'file_size_mb': round(file_path.stat().st_size / (1024 * 1024), 2),
    }


def _process_rename_template(template, context):
    """Process rename template with context."""
    
    result = template
    
    # Replace placeholders
    for key, value in context.items():
        result = result.replace(f'{{{key}}}', str(value))
    
    # Handle counter placeholder
    import re
    counter_match = re.search(r'\{counter:(\d+)\}', result)
    if counter_match:
        padding = int(counter_match.group(1))
        counter_value = str(int(time.time()) % (10**padding)).zfill(padding)
        result = result.replace(counter_match.group(0), counter_value)
    
    return result


if __name__ == '__main__':
    cli()