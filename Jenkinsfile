pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Build image') {
            steps {
                sh 'docker build --tag aceest-fitness:${BUILD_NUMBER} .'
            }
        }
        stage('Test') {
            steps {
                sh 'docker run --rm --entrypoint python aceest-fitness:${BUILD_NUMBER} -m pytest -q'
            }
        }
    }

    post {
        always {
            sh 'docker image rm aceest-fitness:${BUILD_NUMBER} || true'
        }
    }
}