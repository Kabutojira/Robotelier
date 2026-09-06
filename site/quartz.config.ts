import { QuartzConfig } from "./quartz/cfg";
import * as Plugin from "./quartz/plugins";

const config: QuartzConfig = {
  configuration: {
    pageTitle: "Robotelier",
    pageTitleSuffix: " — evidence-backed robotics research",
    enableSPA: true,
    enablePopovers: true,
    analytics: null,
    locale: "en-US",
    baseUrl: process.env.ROBOTELIER_BASE_URL,
    ignorePatterns: ["**/.gitkeep", "_archive", "inbox", "raw", "_meta"],
    defaultDateType: "modified",
    theme: {
      fontOrigin: "local",
      cdnCaching: false,
      typography: {
        header: "system-ui",
        body: "system-ui",
        code: "ui-monospace",
      },
      colors: {
        lightMode: {
          light: "#f8faf9",
          lightgray: "#e1e8e5",
          gray: "#8a9993",
          darkgray: "#3d4c46",
          dark: "#14201b",
          secondary: "#176c57",
          tertiary: "#95621b",
          highlight: "rgba(23, 108, 87, 0.14)",
          textHighlight: "#f2cf5566",
        },
        darkMode: {
          light: "#111714",
          lightgray: "#25302b",
          gray: "#68766f",
          darkgray: "#cad6d0",
          dark: "#f2f7f4",
          secondary: "#60c7a7",
          tertiary: "#e4ae61",
          highlight: "rgba(96, 199, 167, 0.16)",
          textHighlight: "#c99b2966",
        },
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({ priority: ["frontmatter", "git"] }),
      Plugin.SyntaxHighlighting({
        theme: { light: "github-light", dark: "github-dark" },
        keepBackground: false,
      }),
      Plugin.ObsidianFlavoredMarkdown({ enableInHtmlEmbed: false }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({ markdownLinkResolution: "shortest" }),
      Plugin.Description(),
    ],
    filters: [Plugin.RemoveDrafts()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({ enableSiteMap: true, enableRSS: false }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.Favicon(),
      Plugin.NotFoundPage(),
    ],
  },
};

export default config;
