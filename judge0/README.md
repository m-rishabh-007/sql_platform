# Judge0 Submission System

A containerized code execution and submission system based on Judge0, supporting multiple programming languages for competitive programming and coding challenges.

## Features

- **Multi-language Support**: Execute code in various programming languages
- **Docker-based Isolation**: Secure code execution in isolated containers
- **RESTful API**: Easy integration with web applications
- **Production Ready**: Configured with proper logging and monitoring

## Project Structure

```
├── docker-compose.yml    # Docker services configuration
├── judge0.conf          # Judge0 API configuration
├── config/
│   └── puma.rb         # Puma web server configuration
└── log/                # Application logs directory
```

## Quick Start

### Prerequisites

- Docker
- Docker Compose

### Installation

1. Clone the repository:
```bash
git clone https://github.com/m-rishabh-007/judge0-submission-system.git
cd judge0-submission-system
```

2. Start the services:
```bash
docker-compose up -d
```

3. The Judge0 API will be available at `http://localhost:3000`

## Configuration

The system is configured through:
- `judge0.conf`: Main Judge0 API configuration
- `docker-compose.yml`: Service orchestration and environment variables
- `config/puma.rb`: Web server configuration

## Usage

### Submit Code for Execution

```bash
curl -X POST \
  http://localhost:3000/submissions \
  -H 'Content-Type: application/json' \
  -d '{
    "source_code": "print(\"Hello, World!\")",
    "language_id": 71,
    "stdin": ""
  }'
```

### Get Submission Result

```bash
curl -X GET http://localhost:3000/submissions/{submission_id}
```

## Supported Languages

The system supports multiple programming languages including:
- Python (2.7, 3.5, 3.6)
- C/C++
- Java
- JavaScript (Node.js)
- And many more...

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

For issues and questions, please open an issue on GitHub.
