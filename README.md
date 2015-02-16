This is designed to take an RSS/atom feed and filter things in/out of it. YML files are plucked out of s3 (or via http). These contain the configuration for each feed.

## Filters

An **include** filter means only items that match something on theh list will be kept. An **exclude** means matching items will be removed.

## Matches

Individual matches are done against the 'content', 'title', 'summary', and 'link' fields. Text is lowercased. Entries can be string matches or a **regular expression** with slashes at either end. This is useful for URLs.

## Output

In my version, output URLs are prepended with `tedder.me/rss/`. This should probably be configurable in the future.

## Example

The following examples show my personal usage. I've removed a private URL.

    - url: "privateurl"
      filter:
      - include:
        - soup
        - /daily.show/
        - "category: top gear (uk)"
        - mythbusters
        - cats
        exclude:
        - /8.out.of.10.cats/
      output: ted/feed.rss
    - url: http://gdata.youtube.com/feeds/base/users/BuzzFeedVideo/uploads?alt=rss&v=2&orderby=published&client=ytapi-youtube-profile
      filter:
        - include:
          - /dear.kitten/
      output: ted/buzzfeed_dearkitten.rss


