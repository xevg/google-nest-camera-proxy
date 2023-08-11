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


This is a fairly onerous process, so make sure to read the details before you begin. (*There is some more nice documentation of going through the process with screenshots at https://geoffhudik.com/tech/2023/03/04/trying-google-nest-api-with-postman-and-python/*) 


The biggest roadblock is that access to this API requires registering with Google for Device Access https://developers.google.com/nest/device-access/registration. This has a one time $5 fee.

The documentation https://developers.google.com/nest/device-access/get-started walks you through the rest of the process.

I'm not going to cover all the details on how to get this done, because it is documented better elsewhere. Some addition documentation from Google about using their APIs is here:
- https://developers.google.com/nest/device-access/authorize
- https://developers.google.com/nest/device-access/use-the-api
- https://developers.google.com/nest/device-access/api/thermostat

### Basic Instructions 
 
These instructions were taken from the python-google-nest package (https://pypi.org/project/python-google-nest/) which provides the underlying libraries that I use to connect to the cameras. At a high level it involves:
1) Making sure your Nest devices are linked to your Google account 
2) Set up GCP (Google Cloud Platform) account https://console.cloud.google.com/
3) Set up a new GCP project 
   1) Create an Oauth landing page and add your email as a test user 
   2) Enable the Smart device management API
   3) Create an Oauth credential with the settings called from web server and https://www.google.com as the authorized redirect URI. Note the client ID and secret from this step.
4) In https://console.nest.google.com/device-access create a new project and add oauth client ID from step 3.3
5) Follow the series of queries in https://developers.google.com/nest/device-access/authorize to authorize devices. Note This step handled by this library.

Be careful as you follow along the guide in https://developers.google.com/nest/device-access/get-started, since you're dealing with so many similar accounts and keys it can be easy to mix something up, and you won't get particularly useful errors.

You should end up with the following pieces of information:

- project_id
   : ID of the project you created in https://console.nest.google.com/device-access ![Project ID.png](images%2FProject%20ID.png)

- client_id
   : value from setting up OAuth in https://console.cloud.google.com/ project ![Client ID.png](images%2FClient%20ID.png)

- client_secret
   : value from setting up OAuth in https://console.cloud.google.com/ project ![Client Secret.png](images%2FClient%20Secret.png)


You will need those values in the next section.

## Configuration

Most of the configuration lives in a configuration file. Below is a sample file:

```
[AUTH]
    client_id = MYCLIENTID
    client_secret = MYSECRET
    project_id = MYPROJECTID
    access_token_cache_file = /Users/ME/.config/nest/token_cache

[RTSP_SERVER]
    executable = /usr/local/bin/rtsp-simple-server
    config_filename = /Users/ME/.config/nest/rtsp.yml

```
client_id
   : This is the client_id from your project (from the credentials page on the Google console)

client_secret
   : The client secret (from the credentials page on the Google console)

project_id
   : The project ID (from the project page on the Google console)

access_token_cache_file 
   : Where the token cache is stored

executable
   : The location you installed the rtsp-simple-server executable.

config_filename
   : The location of the rtsp-simple-server configuration file. This program adds all the cameras to the configuration file

### Authentication

As part of the pyhon-google-nest package installation that is a dependency of this project, it creates a `nest`application. The first time you run `nest show` it will tell you to go to a URL (https://nestservices.google.com/partnerconnections with some parameters), and then you will step through selecting and authorizing the cameras that you want to stream. When you finish this process your browser will have a URL that looks like https://www.google.com/?state=SOME_STATE_VALUE&code=SOME_AUTHENTICATION_CODE&scope=https://www.googleapis.com/auth/sdm.service that you need to copy and paste into the callback, which is then stored  in the ~/.config/nest/token_cache file. 

## Installation

1) You need to install mediamtx, which you can download at https://github.com/bluenviron/mediamtx. This is the rtsp proxy that I use to translate from Google RTSPS to RTSP. Make a note of where you install it for the configuration file
2) Install this module
```bash 
$ pip install google_nest_camera_proxy
```
3) Edit the configuration file, whose default location is `~/.config/nest/config`. See the Configuration section above for the details. 

## Usage

```
Usage: google_nest_camera_proxy [OPTIONS]

  Configures the proxy rtsp server, and keeps it updated

Options:
  -c, --configuration-file PATH  Where the configuration for this program is located
  -d, --debug                    Turn on debugging output
  --help                         Show this message and exit.

```
## Contributing

Interested in contributing? Check out the contributing guidelines. Please note that this project is released with a Code of Conduct. By contributing to this project, you agree to abide by its terms.

## License

`google_nest_camera_proxy` was created by Xev Gittler. It is licensed under the terms of the MIT license.

## Credits

`google_nest_camera_proxy` was created with [`cookiecutter`](https://cookiecutter.readthedocs.io/en/latest/) and the `py-pkgs-cookiecutter` [template](https://github.com/py-pkgs/py-pkgs-cookiecutter).
