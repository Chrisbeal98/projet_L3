@if "%DEBUG%" == "" @echo off
@rem ##########################################################################
@rem
@rem  Gradle startup script for Windows
@rem
@rem ##########################################################################

@rem Set local scope for the variables with windows NT shell
if "%OS%"=="Windows_NT" setlocal

set DIRNAME=%~dp0
if "%DIRNAME%" == "" set DIRNAME=.
set APP_BASE_NAME=%~n0
set APP_HOME=%DIRNAME%

@rem Resolve any "." and ".." in APP_HOME to make it shorter.
for %%i in ("%APP_HOME%") do set APP_HOME=%%~fi

@rem Define the default Gradle version and distribution URL
set GRADLE_VERSION=8.13
set GRADLE_DIST_URL=https://services.gradle.org/distributions/gradle-8.13-bin.zip

@rem Check if gradle is already installed
where gradle >nul 2>&1
if %ERRORLEVEL% == 0 (
    gradle %*
) else (
    @rem Download Gradle wrapper if not present
    if not exist "%APP_HOME%\gradle\wrapper\gradle-wrapper.jar" (
        echo Downloading Gradle wrapper...
        powershell -Command "Invoke-WebRequest -Uri '%GRADLE_DIST_URL%' -OutFile '%APP_HOME%\gradle\wrapper\gradle-wrapper.jar.tmp'"
        move "%APP_HOME%\gradle\wrapper\gradle-wrapper.jar.tmp" "%APP_HOME%\gradle\wrapper\gradle-wrapper.jar" >nul 2>&1
    )
    
    @rem Use local Gradle distribution or download
    if exist "%APP_HOME%\gradle\wrapper\gradle-wrapper.jar" (
        java -jar "%APP_HOME%\gradle\wrapper\gradle-wrapper.jar" %*
    ) else (
        echo Gradle not found. Please install Gradle or ensure gradle-wrapper.jar exists.
        exit /b 1
    )
)
