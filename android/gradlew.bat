@rem Gradle startup script
@if "%DEBUG%"=="" @echo off
@rem Set local scope
setlocal

set DIRNAME=%~dp0
set APP_BASE_NAME=%~n0
set DEFAULT_JVM_OPTS="-Xmx2048m"
set GRADLE_OPTS=-Dorg.gradle.jvmargs="-Xmx2048m"
set CLASSPATH=%DIRNAME%\gradle\wrapper\gradle-wrapper.jar

if not exist "%CLASSPATH%" (
    echo Gradle wrapper JAR not found at "%CLASSPATH%"
    exit /b 1
)

"%JAVA_HOME%/bin/java.exe" %DEFAULT_JVM_OPTS% %GRADLE_OPTS% -classpath "%CLASSPATH%" org.gradle.wrapper.GradleWrapperMain %*
