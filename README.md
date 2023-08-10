# google_nest_camera_proxy

Proxy your Nest Camera through rtsp-simple-server so you can view it on any RTSP reader.

## How Google Nest Cameras Work

Unfortunately, Google does not let you just connect to an RTSP stream, or even and RTSPS string, and read your cameras. It is much more complicated than that. There are a few hoops that you have to jump through:
1) Go through the Google Device Access Registration Process
2) Get your Google Authentication Tokens
3) Create your configuration files
4) Install mediamtx
5) Run the google-nest-camera-proxy application

Once this process is running what it does is reaches out to Google and gets an authentication token for the RTSPS stream, however that token only lasts for 5 minutes. It also includes an extension token, and this code will extend the token every 4 minutes so that you can record a continuous stream.

## Google Device Access Registration Process 

These were taken from the python-google-nest package (https://pypi.org/project/python-google-nest/) which provides the underlying libraries that I use to connect to the cameras. 

This is a fairly onerous process, so make sure to read the details before you begin. (*There is some more nice documentation of going through the process with screenshots at https://geoffhudik.com/tech/2023/03/04/trying-google-nest-api-with-postman-and-python/*)

The biggest roadblock is that access to this API requires registering with Google for Device Access https://developers.google.com/nest/device-access/registration. This has a one time $5 fee.

The documentation https://developers.google.com/nest/device-access/get-started walks you through the rest of the process.

At a high level it involves:
1) Making sure your Nest devices are linked to your Google account 
1) Set up GCP (Google Cloud Platform) account https://console.cloud.google.com/
1) Set up a new GCP project 

   1. Create a Oauth landing page and add your email as a test user
   1. Enable the Smart device management API
   1. Create an Oauth credential with the settings called from web server and https://www.google.com as the authorized redirect URI. Note the client ID and secret from this step.
4) In https://console.nest.google.com/device-access create a new project and add oauth client ID from step 3.3
5) Follow the series of queries in https://developers.google.com/nest/device-access/authorize to authorize devices. Note This step handled by this library.

Be careful as you follow along the guide in https://developers.google.com/nest/device-access/get-started, since you're dealing with so many similar accounts and keys it can be easy to mix something up and you won't get particularly useful errors.

You should end up with the following pieces of information:

- project_id - ID of the project you created in https://console.nest.google.com/device-access
- client_id - value from setting up OAuth in https://console.cloud.google.com/ project
- client_secret - value from setting up OAuth in https://console.cloud.google.com/ project
you will need those values to use this library.

### Authentication

As part of the pyhon-google-nest package installation that is a dependency of this project, it creates a `nest` application. The first time you run `nest show` it will tell you to go to a URL (https://nestservices.google.com/partnerconnections with some parameters), and then you will step through selecting and authorizing the cameras that you want to stream. When you finish this process your browser will have a URL that looks like https://www.google.com/?state=SOME_STATE_VALUE&code=SOME_AUTHENTICATION_CODE&scope=https://www.googleapis.com/auth/sdm.service that you need to copy and paste into the callback, which is then stored  in the ~/.config/nest/token_cache file. 

## Installation

This package requires you to also install mediamtx, which you can download at https://github.com/bluenviron/mediamtx. This program calls that to proxy the servers.

```bash
$ pip install google_nest_camera_proxy
```

## Configuration instructions


## Usage

- TODO

## Contributing

Interested in contributing? Check out the contributing guidelines. Please note that this project is released with a Code of Conduct. By contributing to this project, you agree to abide by its terms.

## License

`google_nest_camera_proxy` was created by Xev Gittler. It is licensed under the terms of the MIT license.

## Credits

`google_nest_camera_proxy` was created with [`cookiecutter`](https://cookiecutter.readthedocs.io/en/latest/) and the `py-pkgs-cookiecutter` [template](https://github.com/py-pkgs/py-pkgs-cookiecutter).
