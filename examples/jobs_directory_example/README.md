# Jobs Directory Example

This example demonstrates FastJob's automatic job discovery feature - the **zero-configuration** approach to organizing background jobs.

## Project Structure

```
jobs_directory_example/
├── app.py              # Main application that enqueues jobs
├── README.md          # This file
└── jobs/              # 🎯 FastJob finds this automatically!
    ├── __init__.py    # Makes it a Python package
    ├── email.py       # Email-related jobs
    ├── images.py      # Image processing jobs
    └── reports.py     # Report generation jobs
```

## How It Works

**FastJob automatically discovers your jobs** when workers start:

1. **Looks for `jobs/` directory** in your project root
2. **Imports all Python files** in that directory  
3. **Registers functions** decorated with `@fastjob.job()`
4. **No configuration required!**

## Running the Example

### Method 1: Embedded Worker (Development)

```bash
# Set your database URL
export FASTJOB_DATABASE_URL="postgresql://user:pass@localhost/myapp"

# Run with embedded worker (jobs process automatically)
python app.py
```

### Method 2: External Worker (Production-like)

```bash
# Terminal 1: Start worker process
export FASTJOB_DATABASE_URL="postgresql://user:pass@localhost/myapp"
fastjob worker --concurrency 2

# Terminal 2: Enqueue jobs
python app.py --worker-mode=external
```

## Job Organization Examples

### Email Jobs (`jobs/email.py`)
- `send_welcome_email()` - Standard priority
- `send_password_reset_email()` - High priority (urgent queue)
- `send_newsletter()` - Bulk email with retries

### Image Processing (`jobs/images.py`) 
- `resize_image()` - Single image resize
- `generate_thumbnails()` - Multiple thumbnail sizes
- `batch_optimize_images()` - Lower priority batch processing

### Reports (`jobs/reports.py`)
- `generate_daily_report()` - Scheduled daily analytics
- `export_user_data()` - Data export with retry logic
- `analyze_user_behavior()` - Background analysis

## Key Features Demonstrated

✅ **Zero Configuration** - No imports or registration needed  
✅ **Organized Structure** - Jobs grouped by functionality  
✅ **Queue Management** - Different queues for different job types  
✅ **Priority Control** - Urgent jobs vs background tasks  
✅ **Retry Logic** - Automatic retry for failed jobs  
✅ **Scheduled Jobs** - Jobs that run at specific times  

## Advanced: Custom Jobs Module

Want to use a different directory name? Set the environment variable:

```bash
export FASTJOB_JOBS_MODULE="myapp.background_tasks"
```

FastJob will then look for jobs in `myapp/background_tasks/` instead of `jobs/`.

## Production Tips

- **Use external workers** in production: `fastjob worker --concurrency 4`
- **Separate queues** for different priorities: `--queues urgent,default,background`
- **Monitor with CLI**: `fastjob jobs list --status failed`
- **Health checks**: `fastjob health --verbose`

**This is the recommended way to organize FastJob projects!** 🚀